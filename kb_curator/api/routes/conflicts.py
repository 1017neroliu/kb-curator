"""Conflict API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from kb_curator.api.deps import get_db_session
from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import ConflictRead, ConflictType, Severity
from kb_curator.services.crud import (
    create_conflict,
    get_conflict,
    list_conflicts,
)

log = get_logger(__name__)
router = APIRouter(prefix="/knowledge-bases/{kb_id}/conflicts", tags=["Conflicts"])


@router.post("", response_model=ConflictRead, status_code=status.HTTP_201_CREATED)
async def create_conflict_record(
    kb_id: str,
    change_event_id: str,
    new_content: str = "",
    existing_content: str = "",
    existing_entry_id: str | None = None,
    existing_entity_id: str | None = None,
    conflict_type: ConflictType = ConflictType.SEMANTIC,
    severity: Severity = Severity.WARNING,
    session: Annotated[AsyncSession, Depends(get_db_session)] = None,
) -> ConflictRead:
    """Create a new conflict record."""
    summary = f"Conflict detected between new content and existing entry"
    
    try:
        table = await create_conflict(
            session,
            kb_id=kb_id,
            change_event_id=change_event_id,
            conflict_type=conflict_type.value,
            existing_entry_id=existing_entry_id,
            existing_entity_id=existing_entity_id,
            new_content=new_content,
            existing_content=existing_content,
            summary=summary,
            severity=severity.value,
        )
        return _table_to_read(table)
    except Exception as e:
        log.error("create_conflict_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("", response_model=list[ConflictRead])
async def list_conflict_records(
    kb_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ConflictRead]:
    """List conflicts for a knowledge base."""
    try:
        conflicts = await list_conflicts(
            session=session,
            kb_id=kb_id,
            limit=limit,
            offset=offset,
        )
        return [_table_to_read(c) for c in conflicts]
    except Exception as e:
        log.error("list_conflicts_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{conflict_id}", response_model=ConflictRead)
async def get_conflict_record(
    kb_id: str,
    conflict_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ConflictRead:
    """Get a specific conflict."""
    try:
        conflict = await get_conflict(session, conflict_id)
        if not conflict or conflict.kb_id != kb_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conflict not found")
        return _table_to_read(conflict)
    except HTTPException:
        raise
    except Exception as e:
        log.error("get_conflict_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _table_to_read(table) -> ConflictRead:
    """Convert ConflictTable to ConflictRead."""
    return ConflictRead(
        id=table.id,
        kb_id=table.kb_id,
        change_event_id=table.change_event_id,
        conflict_type=ConflictType(table.conflict_type),
        existing_entry_id=table.existing_entry_id,
        existing_entity_id=table.existing_entity_id,
        new_content=table.new_content,
        existing_content=table.existing_content,
        summary=table.summary,
        severity=Severity(table.severity),
        detected_at=table.detected_at,
    )
