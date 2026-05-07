"""Knowledge entry CRUD and semantic search API routes."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from kb_curator.api.deps import SessionDep
from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import (
    EntryStatus,
    KnowledgeEntryCreate,
    KnowledgeEntryRead,
    KnowledgeEntryUpdate,
    SearchRequest,
    SearchResult,
)
from kb_curator.services.crud import (
    count_entries,
    create_entry,
    delete_entry,
    get_entry,
    list_entries,
    update_entry,
)

log = get_logger(__name__)
router = APIRouter(prefix="/knowledge-bases/{kb_id}/entries", tags=["Knowledge Entries"])


def _strip_html(text: str) -> str:
    """Remove HTML markup and return clean text.

    Uses BeautifulSoup to extract visible text, then normalizes whitespace.
    If the content does not look like HTML, returns it unchanged.
    """
    if "<" not in text or ">" not in text:
        return text
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(text, "html.parser")
        # Remove script/style elements
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        clean = soup.get_text(separator="\n")
        # Collapse multiple blank lines
        lines = [ln.strip() for ln in clean.splitlines()]
        lines = [ln for ln in lines if ln]
        return "\n".join(lines)
    except Exception:
        return text


# ============================================================
# Knowledge Entry CRUD
# ============================================================


@router.post("", response_model=KnowledgeEntryRead, status_code=status.HTTP_201_CREATED)
async def create_knowledge_entry(
    kb_id: str,
    body: KnowledgeEntryCreate,
    session: SessionDep,
) -> KnowledgeEntryRead:
    """Create a new knowledge entry."""
    if body.kb_id != kb_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="kb_id mismatch",
        )
    try:
        table = await create_entry(session, **body.model_dump())
        return _table_to_read(table)
    except Exception as e:
        log.error("create_entry_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("", response_model=list[KnowledgeEntryRead])
async def list_knowledge_entries(
    kb_id: str,
    session: SessionDep,
    entry_status: EntryStatus | None = Query(None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[KnowledgeEntryRead]:
    """List knowledge entries for a knowledge base."""
    entries = await list_entries(
        session=session,
        kb_id=kb_id,
        status=entry_status.value if entry_status else None,
        limit=limit,
        offset=offset,
    )
    return [_table_to_read(e) for e in entries]


# ============================================================
# Fixed-path endpoints (MUST be before /{entry_id} routes)
# ============================================================


@router.get("/count")
async def count_knowledge_entries(
    kb_id: str,
    session: SessionDep,
    entry_status: EntryStatus | None = Query(None, alias="status"),
) -> dict:
    """Count knowledge entries for a knowledge base."""
    total = await count_entries(
        session=session,
        kb_id=kb_id,
        status=entry_status.value if entry_status else None,
    )
    return {"kb_id": kb_id, "count": total}


ALLOWED_EXTENSIONS = {".txt", ".md", ".json", ".yaml", ".yml", ".csv", ".html", ".xml", ".rst"}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: str,
    session: SessionDep,
    file: UploadFile = File(...),
    source_id: str = Form("upload"),
    auto_process: bool = Form(True),
) -> dict:
    """Upload a document file, create a knowledge entry, and optionally process it.

    Supported file types: .txt, .md, .json, .yaml, .yml, .csv, .html, .xml, .rst
    """
    # Validate file extension
    filename = file.filename or "unknown.txt"
    _, ext = os.path.splitext(filename)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read file content
    try:
        content_bytes = await file.read()
        content = content_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {str(e)}",
        )

    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
        )

    # Create knowledge entry
    title = os.path.splitext(filename)[0]
    entry_id = uuid4().hex
    try:
        entry = await create_entry(
            session,
            id=entry_id,
            kb_id=kb_id,
            title=title,
            content=content,
            source_id=source_id,
            source_url=f"upload://{filename}",
            tags=["uploaded"],
            metadata_json={"original_filename": filename, "file_extension": ext},
        )
    except Exception as e:
        log.error("upload_create_entry_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    result_summary = {
        "entry_id": entry.id,
        "title": title,
        "filename": filename,
        "content_length": len(content),
        "processed": False,
        "chunks": 0,
        "entities": 0,
        "relations": 0,
    }

    # Auto-process if requested
    if auto_process:
        try:
            from kb_curator.services.knowledge_extractor import create_extractor

            extractor = create_extractor(kb_id=kb_id, source_id=source_id)
            result = await extractor.extract_and_store(
                text=_strip_html(content),
                entry_id=entry.id,
            )

            # Update entry metadata
            existing_meta = {"original_filename": filename, "file_extension": ext}
            existing_meta["processed"] = True
            existing_meta["processed_at"] = datetime.utcnow().isoformat()
            existing_meta["extraction_summary"] = {
                "chunks": len(result.text_chunks),
                "entities": len(result.entities),
                "relations": len(result.relations),
            }
            await update_entry(session, entry.id, metadata=existing_meta)

            result_summary["processed"] = True
            result_summary["chunks"] = len(result.text_chunks)
            result_summary["entities"] = len(result.entities)
            result_summary["relations"] = len(result.relations)
            result_summary["errors"] = result.errors
        except Exception as e:
            log.error("upload_process_failed", entry_id=entry.id, error=str(e))
            result_summary["processing_error"] = str(e)

    return result_summary


@router.post("/search", response_model=list[SearchResult])
async def search_entries(
    kb_id: str,
    body: SearchRequest,
    session: SessionDep,
) -> list[SearchResult]:
    """Semantic search across knowledge entries.

    Uses the FAISS vector store to find the most similar entries to the query.
    """
    try:
        from kb_curator.services.embedding_service import get_embedding_service
        from kb_curator.services.vector_store import get_vector_store

        embedding_svc = get_embedding_service()
        query_embedding = await embedding_svc.embed(body.query)

        vector_store = get_vector_store(kb_id)
        raw_results = vector_store.search(
            query_embedding=query_embedding,
            top_k=body.top_k,
            kb_id=kb_id,
        )

        results = []
        hit_entry_ids: set[str] = set()
        for r in raw_results:
            meta = r.get("metadata", {})
            # Apply filters if specified
            if body.filters:
                skip = False
                for key, value in body.filters.items():
                    if meta.get(key) != value:
                        skip = True
                        break
                if skip:
                    continue

            entry_id = meta.get("entry_id", "")
            hit_entry_ids.add(entry_id)
            # Fetch content from metadata or DB
            content = meta.get("content", "")
            if not content and entry_id:
                db_entry = await get_entry(session, entry_id)
                if db_entry:
                    content = db_entry.content

            results.append(SearchResult(
                entry_id=entry_id,
                content=content,
                score=r.get("score", 0.0),
                metadata=meta,
            ))

        # Update search_count and hit_count for all active entries in this KB
        try:
            all_entries = await list_entries(session, kb_id, status="active", limit=1000)
            for entry in all_entries:
                existing_meta = {}
                if entry.metadata_json:
                    existing_meta = json.loads(entry.metadata_json) if isinstance(entry.metadata_json, str) else entry.metadata_json
                existing_meta["search_count"] = existing_meta.get("search_count", 0) + 1
                if entry.id in hit_entry_ids:
                    existing_meta["hit_count"] = existing_meta.get("hit_count", 0) + 1
                await update_entry(session, entry.id, metadata=existing_meta)
        except Exception as e:
            log.warning("search_stats_update_failed", error=str(e))

        return results
    except Exception as e:
        log.error("search_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ============================================================
# Dynamic path endpoints (after fixed paths)
# ============================================================


@router.get("/{entry_id}", response_model=KnowledgeEntryRead)
async def get_knowledge_entry(
    kb_id: str,
    entry_id: str,
    session: SessionDep,
) -> KnowledgeEntryRead:
    """Get a specific knowledge entry."""
    entry = await get_entry(session, entry_id)
    if not entry or entry.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return _table_to_read(entry)


@router.patch("/{entry_id}", response_model=KnowledgeEntryRead)
async def update_knowledge_entry(
    kb_id: str,
    entry_id: str,
    body: KnowledgeEntryUpdate,
    session: SessionDep,
) -> KnowledgeEntryRead:
    """Update a knowledge entry."""
    entry = await get_entry(session, entry_id)
    if not entry or entry.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        return _table_to_read(entry)

    try:
        updated = await update_entry(session, entry_id, **update_data)
        if not updated:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update entry")
        return _table_to_read(updated)
    except HTTPException:
        raise
    except Exception as e:
        log.error("update_entry_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{entry_id}", status_code=status.HTTP_200_OK)
async def delete_knowledge_entry(
    kb_id: str,
    entry_id: str,
    session: SessionDep,
) -> dict:
    """Delete a knowledge entry."""
    entry = await get_entry(session, entry_id)
    if not entry or entry.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    await delete_entry(session, entry_id)
    return {"status": "deleted", "entry_id": entry_id}


@router.post("/{entry_id}/process")
async def process_knowledge_entry(
    kb_id: str,
    entry_id: str,
    session: SessionDep,
) -> dict:
    """Process a knowledge entry: extract chunks, embeddings, entities, and relations.

    This triggers the full knowledge extraction pipeline for an existing entry,
    storing results in FAISS (vector store) and Neo4j (knowledge graph).
    """
    entry = await get_entry(session, entry_id)
    if not entry or entry.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

    try:
        from kb_curator.services.knowledge_extractor import create_extractor

        # Strip HTML if the content looks like markup
        text = _strip_html(entry.content)
        log.info("process_entry_text_prepared",
                 entry_id=entry_id,
                 original_len=len(entry.content),
                 cleaned_len=len(text))

        extractor = create_extractor(kb_id=kb_id, source_id=entry.source_id)
        result = await extractor.extract_and_store(
            text=text,
            entry_id=entry_id,
        )

        # Update entry metadata to mark as processed
        existing_meta = {}
        if hasattr(entry, 'metadata_json') and entry.metadata_json:
            existing_meta = json.loads(entry.metadata_json) if isinstance(entry.metadata_json, str) else entry.metadata_json

        existing_meta["processed"] = True
        existing_meta["processed_at"] = datetime.utcnow().isoformat()
        existing_meta["extraction_summary"] = {
            "chunks": len(result.text_chunks),
            "entities": len(result.entities),
            "relations": len(result.relations),
        }

        await update_entry(session, entry_id, metadata=existing_meta)

        return {
            "entry_id": entry_id,
            "status": "processed",
            "chunks": len(result.text_chunks),
            "entities": len(result.entities),
            "relations": len(result.relations),
            "errors": result.errors,
        }
    except Exception as e:
        log.error("process_entry_failed", entry_id=entry_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ============================================================
# Conversion helper
# ============================================================


def _table_to_read(table) -> KnowledgeEntryRead:
    """Convert KnowledgeEntryTable to KnowledgeEntryRead."""
    tags = table.tags
    if isinstance(tags, str):
        tags = json.loads(tags)
    metadata = table.metadata_json
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return KnowledgeEntryRead(
        id=table.id,
        kb_id=table.kb_id,
        title=table.title,
        content=table.content,
        source_id=table.source_id,
        source_url=table.source_url,
        version=table.version,
        status=EntryStatus(table.status),
        tags=tags,
        created_at=table.created_at,
        updated_at=table.updated_at,
        expires_at=table.expires_at,
        metadata=metadata,
    )
