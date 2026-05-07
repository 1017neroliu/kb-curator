"""ChangeEvent API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from kb_curator.api.deps import get_db_session
from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import ChangeEventCreate, ChangeEventRead, ChangeType
from kb_curator.services.crud import (
    create_change_event,
    get_change_event,
    list_change_events,
)

log = get_logger(__name__)
router = APIRouter(prefix="/knowledge-bases/{kb_id}/events", tags=["Change Events"])


@router.post("", response_model=ChangeEventRead, status_code=status.HTTP_201_CREATED)
async def create_event(
    kb_id: str,
    event: ChangeEventCreate,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChangeEventRead:
    """Create a new change event."""
    if event.kb_id != kb_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="kb_id mismatch",
        )

    try:
        table = await create_change_event(session, **event.model_dump())
        return _table_to_read(table)
    except Exception as e:
        log.error("create_event_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("", response_model=list[ChangeEventRead])
async def list_events(
    kb_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    change_type: ChangeType | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ChangeEventRead]:
    """List change events for a knowledge base."""
    try:
        events = await list_change_events(
            session=session,
            kb_id=kb_id,
            change_type=change_type.value if change_type else None,
            limit=limit,
            offset=offset,
        )
        return [_table_to_read(e) for e in events]
    except Exception as e:
        log.error("list_events_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{event_id}", response_model=ChangeEventRead)
async def get_event(
    kb_id: str,
    event_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChangeEventRead:
    """Get a specific change event."""
    try:
        event = await get_change_event(session, event_id)
        if not event or event.kb_id != kb_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        return _table_to_read(event)
    except HTTPException:
        raise
    except Exception as e:
        log.error("get_event_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _table_to_read(table) -> ChangeEventRead:
    """Convert ChangeEventTable to ChangeEventRead."""
    import json as json_module
    return ChangeEventRead(
        id=table.id,
        kb_id=table.kb_id,
        source_id=table.source_id,
        change_type=ChangeType(table.change_type),
        title=table.title,
        content_before=table.content_before,
        content_after=table.content_after,
        detected_at=table.detected_at,
    )
