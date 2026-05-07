"""LangGraph agent for knowledge base maintenance."""

from __future__ import annotations

from typing import Any, TypedDict
from uuid import uuid4

from kb_curator.core.logging import get_logger

log = get_logger(__name__)


class AgentState(TypedDict, total=False):
    """State passed between nodes in the agent graph."""
    kb_id: str
    change_event_id: str | None
    change_type: str | None
    entry_id: str | None
    content: str | None
    extracted_entities: list[dict]
    extracted_relations: list[dict]
    text_chunks: list[dict]
    conflicts: list[dict]
    has_conflict: bool
    review_task_id: str | None
    human_decision: dict | None
    update_plan: dict | None
    execution_result: dict | None
    errors: list[str]
    metadata: dict[str, Any]


# Node function signatures
async def receive_event(state: AgentState) -> AgentState:
    """Receive a change event and initialize state."""
    log.info("node_receive_event", kb_id=state.get("kb_id"), event_id=state.get("change_event_id"))
    if "errors" not in state:
        state["errors"] = []
    if "extracted_entities" not in state:
        state["extracted_entities"] = []
    if "extracted_relations" not in state:
        state["extracted_relations"] = []
    if "text_chunks" not in state:
        state["text_chunks"] = []
    if "conflicts" not in state:
        state["conflicts"] = []
    state["has_conflict"] = False

    # Load entry content if entry_id is provided
    entry_id = state.get("entry_id")
    kb_id = state.get("kb_id")
    if entry_id and kb_id and not state.get("content"):
        try:
            from kb_curator.services.crud import get_entry
            from kb_curator.services.db import get_session_factory
            factory = get_session_factory()
            async with factory() as session:
                entry = await get_entry(session, entry_id)
                if entry and entry.kb_id == kb_id:
                    state["content"] = entry.content
                    state["change_type"] = state.get("change_type") or "new_info"
        except Exception as e:
            log.error("receive_event_load_entry_failed", error=str(e))
            state["errors"].append(str(e))

    return state


async def classify_change(state: AgentState) -> AgentState:
    """Classify the type of change event."""
    log.info("node_classify_change", kb_id=state.get("kb_id"))
    # If change_type is already set (e.g. from event metadata), keep it.
    # Otherwise default to "new_info".
    if not state.get("change_type"):
        state["change_type"] = "new_info"
    log.info("change_classified", change_type=state["change_type"])
    return state


async def extract_knowledge(state: AgentState) -> AgentState:
    """Extract entities and relations from changed content."""
    log.info("node_extract_knowledge", kb_id=state.get("kb_id"))
    content = state.get("content", "")
    kb_id = state.get("kb_id", "")
    entry_id = state.get("entry_id", "")

    if not content:
        log.warning("no_content_to_extract")
        return state

    try:
        from kb_curator.services.knowledge_extractor import create_extractor

        source_id = entry_id or "agent"
        extractor = create_extractor(kb_id=kb_id, source_id=source_id)

        # Strip HTML if needed
        text = content
        if "<" in text and ">" in text:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                clean = soup.get_text(separator="\n")
                lines = [ln.strip() for ln in clean.splitlines()]
                lines = [ln for ln in lines if ln]
                text = "\n".join(lines)
            except Exception:
                pass

        # Use extract_and_store to persist results to FAISS + Neo4j
        result = await extractor.extract_and_store(text=text, entry_id=entry_id)

        state["extracted_entities"] = [
            {"id": e.id, "name": e.name, "entity_type": e.entity_type}
            for e in result.entities
        ]
        state["extracted_relations"] = [
            {
                "source_entity_id": r.source_entity_id,
                "target_entity_id": r.target_entity_id,
                "relation_type": r.relation_type,
            }
            for r in result.relations
        ]
        state["text_chunks"] = [
            {"id": c.id, "content": c.content[:100]}
            for c in result.text_chunks
        ]
        if result.errors:
            state["errors"].extend(result.errors)

        log.info(
            "knowledge_extracted",
            entities=len(result.entities),
            relations=len(result.relations),
            chunks=len(result.text_chunks),
        )
    except Exception as e:
        log.error("extract_knowledge_failed", error=str(e))
        state["errors"].append(f"Knowledge extraction failed: {e}")

    return state


async def detect_conflicts(state: AgentState) -> AgentState:
    """Detect conflicts with existing knowledge."""
    log.info("node_detect_conflicts", kb_id=state.get("kb_id"))
    kb_id = state.get("kb_id", "")
    entities = state.get("extracted_entities", [])

    if not entities:
        state["has_conflict"] = False
        return state

    try:
        from kb_curator.services.conflict_detector import ConflictDetector

        detector = ConflictDetector(kb_id=kb_id)

        # Check for structural conflicts between new entities and existing ones
        conflicts = []
        for ent in entities:
            try:
                entity_conflicts = await detector.detect_structural_conflicts(
                    entity_name=ent.get("name", ""),
                    entity_type=ent.get("entity_type", ""),
                    properties={},
                )
                conflicts.extend(entity_conflicts)
            except Exception as e:
                log.warning("conflict_check_entity_failed", entity=ent.get("name"), error=str(e))

        # Deduplicate by conflict description
        seen = set()
        unique_conflicts = []
        for c in conflicts:
            key = c.get("description", str(c))
            if key not in seen:
                seen.add(key)
                unique_conflicts.append(c)

        state["conflicts"] = unique_conflicts
        state["has_conflict"] = len(unique_conflicts) > 0

        log.info("conflicts_detected", count=len(unique_conflicts))
    except Exception as e:
        log.warning("conflict_detection_failed", error=str(e))
        # If conflict detection fails, proceed without blocking
        state["has_conflict"] = False

    return state


async def create_review_task(state: AgentState) -> AgentState:
    """Create a human review task for conflict resolution."""
    log.info("node_create_review", kb_id=state.get("kb_id"))
    kb_id = state.get("kb_id", "")
    conflicts = state.get("conflicts", [])

    try:
        from kb_curator.services.crud import create_review_task as crud_create_review
        from kb_curator.services.db import get_session_factory
        from kb_curator.core.config import get_settings

        settings = get_settings()
        task_id = uuid4().hex
        title = f"知识冲突待审核（{len(conflicts)} 个冲突）"
        descriptions = "; ".join(c.get("description", "")[:80] for c in conflicts[:3])
        if len(conflicts) > 3:
            descriptions += f"... 等 {len(conflicts)} 个"

        factory = get_session_factory()
        async with factory() as session:
            table = await crud_create_review(
                session,
                id=task_id,
                kb_id=kb_id,
                conflict_id=conflicts[0].get("id", "") if conflicts else "",
                task_type="conflict_resolution",
                title=title,
                description=descriptions,
                assigned_to="pending",
            )
            state["review_task_id"] = table.id
            log.info("review_task_created", task_id=table.id)
    except Exception as e:
        log.error("create_review_task_failed", error=str(e))
        state["review_task_id"] = None
        state["errors"].append(f"Failed to create review task: {e}")

    return state


async def wait_for_decision(state: AgentState) -> AgentState:
    """Wait for human decision (interrupted state)."""
    log.info("node_wait_for_decision", kb_id=state.get("kb_id"))
    return state


async def apply_update(state: AgentState) -> AgentState:
    """Apply the update plan to vector store and graph store."""
    log.info("node_apply_update", kb_id=state.get("kb_id"))
    operations = []

    # If there's a human decision, apply it
    decision = state.get("human_decision")
    if decision:
        decision_type = decision.get("decision_type", "")
        log.info("applying_human_decision", decision_type=decision_type)

    entities_count = len(state.get("extracted_entities", []))
    relations_count = len(state.get("extracted_relations", []))
    chunks_count = len(state.get("text_chunks", []))

    if entities_count > 0 or relations_count > 0:
        operations.append(f"Stored {entities_count} entities and {relations_count} relations")
    if chunks_count > 0:
        operations.append(f"Stored {chunks_count} text chunks in vector store")

    state["execution_result"] = {
        "success": True,
        "operations": operations,
        "entities": entities_count,
        "relations": relations_count,
        "chunks": chunks_count,
    }
    return state


async def log_result(state: AgentState) -> AgentState:
    """Log the final result of the agent execution."""
    result = state.get("execution_result", {})
    log.info(
        "node_log_result",
        kb_id=state.get("kb_id"),
        success=result.get("success"),
        entities=result.get("entities", 0),
        relations=result.get("relations", 0),
        errors=len(state.get("errors", [])),
    )
    return state


# Conditional routing functions
def should_interrupt(state: AgentState) -> str:
    """Determine if we should interrupt for human review."""
    if state.get("has_conflict"):
        return "create_review"
    return "apply_update"


def after_review(state: AgentState) -> str:
    """Determine next step after human decision."""
    return "apply_update"


def route_after_classify(state: AgentState) -> str:
    """Route after classification."""
    change_type = state.get("change_type", "")
    if change_type == "redundant":
        return "log_result"  # Skip
    return "extract_knowledge"
