"""Knowledge base management API routes.

Provides endpoints for managing knowledge bases (logical namespaces).
Each knowledge base is identified by a kb_id and is isolated from others.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from kb_curator.api.deps import SessionDep
from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import EntryStatus
from kb_curator.services.crud import (
    count_entries,
    list_data_sources,
    list_entries,
)

log = get_logger(__name__)
router = APIRouter(prefix="/knowledge-bases", tags=["Knowledge Bases"])


class KnowledgeBaseInfo:
    """Summary info for a knowledge base."""

    def __init__(
        self,
        kb_id: str,
        total_entries: int,
        active_entries: int,
        archived_entries: int,
        deprecated_entries: int,
        data_sources_count: int,
    ):
        self.kb_id = kb_id
        self.total_entries = total_entries
        self.active_entries = active_entries
        self.archived_entries = archived_entries
        self.deprecated_entries = deprecated_entries
        self.data_sources_count = data_sources_count


class KnowledgeBaseInfoResponse:
    """Response model for KB info."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@router.get("/{kb_id}")
async def get_knowledge_base(
    kb_id: str,
    session: SessionDep,
) -> dict:
    """Get summary information about a knowledge base."""
    try:
        total = await count_entries(session, kb_id)
        active = await count_entries(session, kb_id, status="active")
        archived = await count_entries(session, kb_id, status="archived")
        deprecated = await count_entries(session, kb_id, status="deprecated")
        sources = await list_data_sources(session, kb_id)

        return {
            "kb_id": kb_id,
            "total_entries": total,
            "active_entries": active,
            "archived_entries": archived,
            "deprecated_entries": deprecated,
            "data_sources_count": len(sources),
        }
    except Exception as e:
        log.error("get_kb_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("")
async def list_knowledge_bases(
    session: SessionDep,
) -> dict:
    """List all known knowledge base IDs.

    This scans the knowledge_entries table for distinct kb_id values.
    """
    try:
        from sqlalchemy import select, func, distinct
        from kb_curator.models.db_tables import KnowledgeEntryTable

        result = await session.execute(
            select(distinct(KnowledgeEntryTable.kb_id))
        )
        kb_ids = [row[0] for row in result.all()]
        return {"knowledge_bases": kb_ids}
    except Exception as e:
        log.error("list_kbs_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{kb_id}", status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    kb_id: str,
) -> dict:
    """Initialize a new knowledge base.

    This creates the directory structure for the vector store.
    The knowledge base is implicitly created when entries are added.
    """
    try:
        from pathlib import Path
        from kb_curator.core.config import get_settings

        settings = get_settings()
        kb_dir = settings.vector_store.faiss_index_path / kb_id
        kb_dir.mkdir(parents=True, exist_ok=True)

        return {"kb_id": kb_id, "status": "created"}
    except Exception as e:
        log.error("create_kb_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{kb_id}", status_code=status.HTTP_200_OK)
async def delete_knowledge_base(
    kb_id: str,
    session: SessionDep,
    confirm: bool = Query(False, description="Must be true to confirm deletion"),
) -> dict:
    """Delete a knowledge base and all its data.

    This is a destructive operation that removes all entries, events,
    conflicts, review tasks, and vector store data for the given kb_id.
    """
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set confirm=true to acknowledge destructive deletion",
        )

    try:
        from sqlalchemy import delete as sa_delete, select as sa_select
        from kb_curator.models.db_tables import (
            ChangeEventTable,
            ConflictTable,
            DecisionTable,
            KnowledgeEntryTable,
            QualityReportTable,
            ReviewTaskTable,
            DataSourceTable,
        )
        from kb_curator.services.vector_store import reset_vector_stores

        # Get review task IDs for this kb_id (needed to delete decisions)
        result = await session.execute(
            sa_select(ReviewTaskTable.id).where(ReviewTaskTable.kb_id == kb_id)
        )
        task_ids = [row[0] for row in result.all()]

        # Delete all associated data in order (respecting FK-like dependencies)
        # Decisions first (reference review tasks)
        if task_ids:
            await session.execute(sa_delete(DecisionTable).where(
                DecisionTable.review_task_id.in_(task_ids)
            ))
        # Review tasks
        await session.execute(sa_delete(ReviewTaskTable).where(ReviewTaskTable.kb_id == kb_id))
        # Conflicts
        await session.execute(sa_delete(ConflictTable).where(ConflictTable.kb_id == kb_id))
        # Change events
        await session.execute(sa_delete(ChangeEventTable).where(ChangeEventTable.kb_id == kb_id))
        # Knowledge entries
        await session.execute(sa_delete(KnowledgeEntryTable).where(KnowledgeEntryTable.kb_id == kb_id))
        # Quality reports
        await session.execute(sa_delete(QualityReportTable).where(QualityReportTable.kb_id == kb_id))
        # Data sources
        await session.execute(sa_delete(DataSourceTable).where(DataSourceTable.kb_id == kb_id))

        await session.commit()

        # Clean up vector store
        try:
            reset_vector_stores()
        except Exception:
            pass

        log.info("kb_deleted", kb_id=kb_id)
        return {"status": "deleted", "kb_id": kb_id}
    except Exception as e:
        log.error("delete_kb_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
