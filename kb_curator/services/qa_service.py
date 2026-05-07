"""QA (Question Answering) service.

Retrieval-augmented generation: embed query → vector search → graph expand →
assemble context → LLM generate answer.
"""

from __future__ import annotations

import json
from typing import AsyncGenerator

import litellm

from kb_curator.core.config import get_settings
from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import (
    ChatMessage,
    QARequest,
    QAResponse,
    QASource,
)
from kb_curator.services.crud import get_entry
from kb_curator.services.db import get_session_factory
from kb_curator.services.embedding_service import get_embedding_service
from kb_curator.services.graph_store import get_graph_store
from kb_curator.services.vector_store import get_vector_store

log = get_logger(__name__)


class QAService:
    """Core QA logic: retrieve relevant context and generate answers."""

    async def answer(self, request: QARequest) -> QAResponse:
        """Non-streaming QA: returns the full answer at once."""
        settings = get_settings()
        qa_cfg = settings.qa

        # 1. Embed the question
        emb_svc = get_embedding_service()
        query_emb = await emb_svc.embed(request.question)

        # 2. Vector search
        top_k = request.top_k or qa_cfg.top_k
        vs = get_vector_store(request.kb_id)
        raw_results = vs.search(
            query_embedding=query_emb,
            top_k=top_k,
            kb_id=request.kb_id,
        )

        # Build vector sources and collect entry_ids
        vector_sources: list[QASource] = []
        entry_ids: set[str] = set()
        for r in raw_results:
            meta = r.get("metadata", {})
            eid = meta.get("entry_id")
            if eid:
                entry_ids.add(eid)
            vector_sources.append(QASource(
                source_type="vector",
                chunk_id=r.get("chunk_id"),
                entry_id=eid,
                content=meta.get("content"),
                score=r.get("score"),
            ))

        # 3. Expand graph context from entry_ids
        graph_sources = await self._expand_graph_context(
            request.kb_id, entry_ids, qa_cfg.graph_expand_limit
        )

        # 4. Assemble context string
        all_sources = vector_sources + graph_sources
        context = await self._assemble_context(request.kb_id, vector_sources, graph_sources, qa_cfg.context_max_chars)

        # 5. Build LLM messages
        messages = self._build_messages(request.question, request.history, context)

        # 6. Call LLM (non-streaming)
        from kb_curator.services.llm import completion
        answer_text = await completion(
            messages=messages,
            temperature=qa_cfg.qa_temperature,
        )

        return QAResponse(
            answer=answer_text,
            sources=all_sources,
            question=request.question,
            kb_id=request.kb_id,
        )

    async def answer_stream(self, request: QARequest) -> AsyncGenerator[str, None]:
        """Streaming QA: yields SSE-formatted events.

        Yields:
            - sources event:  data: {"type":"sources","sources":[...]}
            - token events:   data: {"type":"token","content":"..."}
            - done event:     data: [DONE]
        """
        settings = get_settings()
        qa_cfg = settings.qa

        # 1. Embed the question
        emb_svc = get_embedding_service()
        query_emb = await emb_svc.embed(request.question)

        # 2. Vector search
        top_k = request.top_k or qa_cfg.top_k
        vs = get_vector_store(request.kb_id)
        raw_results = vs.search(
            query_embedding=query_emb,
            top_k=top_k,
            kb_id=request.kb_id,
        )

        vector_sources: list[QASource] = []
        entry_ids: set[str] = set()
        for r in raw_results:
            meta = r.get("metadata", {})
            eid = meta.get("entry_id")
            if eid:
                entry_ids.add(eid)
            vector_sources.append(QASource(
                source_type="vector",
                chunk_id=r.get("chunk_id"),
                entry_id=eid,
                content=meta.get("content"),
                score=r.get("score"),
            ))

        # 3. Expand graph context
        graph_sources = await self._expand_graph_context(
            request.kb_id, entry_ids, qa_cfg.graph_expand_limit
        )

        all_sources = vector_sources + graph_sources

        # 4. Emit sources event first
        sources_data = [s.model_dump() for s in all_sources]
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data}, ensure_ascii=False)}\n\n"

        # 5. Assemble context
        context = await self._assemble_context(request.kb_id, vector_sources, graph_sources, qa_cfg.context_max_chars)

        # 6. Build messages and stream LLM response
        messages = self._build_messages(request.question, request.history, context)

        llm_settings = settings.llm
        stream = await litellm.acompletion(
            model=llm_settings.model,
            messages=messages,
            temperature=qa_cfg.qa_temperature,
            max_tokens=llm_settings.max_tokens,
            timeout=llm_settings.timeout_seconds,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                token_data = json.dumps({"type": "token", "content": delta.content}, ensure_ascii=False)
                yield f"data: {token_data}\n\n"

        yield "data: [DONE]\n\n"

    async def _expand_graph_context(
        self,
        kb_id: str,
        entry_ids: set[str],
        limit: int,
    ) -> list[QASource]:
        """Expand graph context by looking up entities associated with entries
        and fetching their neighbors."""
        if not entry_ids:
            return []

        graph_sources: list[QASource] = []
        try:
            gs = get_graph_store()
            seen_entities: set[str] = set()

            for entry_id in entry_ids:
                entities = await gs.get_entities_by_entry(entry_id, kb_id)
                for ent_record in entities[:limit]:
                    ent = ent_record.get("e", ent_record) if isinstance(ent_record, dict) else ent_record
                    entity_id = ent.get("id") if isinstance(ent, dict) else getattr(ent, "id", None)
                    entity_name = ent.get("name") if isinstance(ent, dict) else getattr(ent, "name", None)

                    if not entity_id or entity_id in seen_entities:
                        continue
                    seen_entities.add(entity_id)

                    # Get neighbors
                    neighbors = await gs.get_entity_neighbors(entity_id, kb_id)
                    for nb in neighbors:
                        graph_sources.append(QASource(
                            source_type="graph",
                            entity_id=entity_id,
                            entity_name=entity_name,
                            relation_type=nb.get("relation_type"),
                            neighbor_name=nb.get("neighbor_name"),
                        ))
                        if len(graph_sources) >= limit:
                            return graph_sources
        except Exception as e:
            log.warning("graph_expand_failed", error=str(e))

        return graph_sources

    async def _fetch_entry_content(self, entry_id: str) -> str | None:
        """Fetch the original content of a knowledge entry from SQLite."""
        try:
            factory = get_session_factory()
            async with factory() as session:
                entry = await get_entry(session, entry_id)
                if entry:
                    return entry.content
        except Exception as e:
            log.warning("fetch_entry_content_failed", entry_id=entry_id, error=str(e))
        return None

    async def _assemble_context(
        self,
        kb_id: str,
        vector_sources: list[QASource],
        graph_sources: list[QASource],
        max_chars: int,
    ) -> str:
        """Assemble numbered context from vector and graph sources."""
        parts: list[str] = []
        current_len = 0

        # Vector sources
        for i, src in enumerate(vector_sources, 1):
            content = src.content
            # If content is not in source metadata, fetch from SQLite
            if not content and src.entry_id:
                content = await self._fetch_entry_content(src.entry_id)

            if content:
                snippet = content[:500] if len(content) > 500 else content
                line = f"[{i}] (向量检索, score={src.score:.3f}) {snippet}"
                if current_len + len(line) > max_chars:
                    break
                parts.append(line)
                current_len += len(line)

        # Graph sources
        offset = len(parts)
        for i, src in enumerate(graph_sources, offset + 1):
            if src.entity_name and src.neighbor_name:
                line = f"[{i}] (图谱关系) {src.entity_name} --[{src.relation_type}]--> {src.neighbor_name}"
                if current_len + len(line) > max_chars:
                    break
                parts.append(line)
                current_len += len(line)

        if not parts:
            return "（未找到相关知识内容）"

        return "\n".join(parts)

    def _build_messages(
        self,
        question: str,
        history: list[ChatMessage],
        context: str,
    ) -> list[dict[str, str]]:
        """Build the LLM message list from question, history, and context."""
        system_msg = (
            "你是一个知识库问答助手。根据下方提供的参考内容回答用户问题。\n"
            "要求：\n"
            "1. 仅根据参考内容回答，不要编造信息\n"
            "2. 如果参考内容不足以回答问题，明确说明\n"
            "3. 引用来源时使用 [编号] 格式\n"
            "4. 用中文回答\n"
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_msg},
        ]

        # Add conversation history
        for msg in history[-10:]:  # Keep last 10 messages for context window
            messages.append({"role": msg.role, "content": msg.content})

        # Add current question with context
        user_msg = f"参考内容：\n{context}\n\n问题：{question}"
        messages.append({"role": "user", "content": user_msg})

        return messages


# Singleton
_qa_service: QAService | None = None


def get_qa_service() -> QAService:
    """Get or create the singleton QAService instance."""
    global _qa_service
    if _qa_service is None:
        _qa_service = QAService()
    return _qa_service
