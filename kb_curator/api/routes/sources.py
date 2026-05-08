"""Data source management API routes."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from kb_curator.api.deps import SessionDep
from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import DataSourceCreate, DataSourceRead
from kb_curator.services.crud import (
    create_data_source,
    delete_data_source,
    get_data_source,
    list_data_sources,
    update_data_source,
)
from pydantic import BaseModel


class DataSourceUpdate(BaseModel):
    """Request body for updating a data source."""
    name: str | None = None
    connection_config: dict | None = None
    poll_interval_minutes: int | None = None
    enabled: bool | None = None

log = get_logger(__name__)
router = APIRouter(prefix="/knowledge-bases/{kb_id}/sources", tags=["Data Sources"])


def _validate_connection_config(source_type: str, config: dict) -> None:
    """Validate required connection_config fields for each source type.

    Raises:
        HTTPException (400): If required fields are missing.
    """
    required_map: dict[str, list[str]] = {
        "wiki": ["url"],
        "confluence": ["url", "username", "api_token"],
        "jira": ["url", "username", "api_token"],
        "webpage": ["urls"],
    }
    required = required_map.get(source_type)
    if not required:
        return  # file and conversation_log have no strict requirements here

    missing = [f for f in required if not config.get(f)]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required connection_config fields for {source_type}: {', '.join(missing)}",
        )


@router.post("", response_model=DataSourceRead, status_code=status.HTTP_201_CREATED)
async def create_source(
    kb_id: str,
    body: DataSourceCreate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> DataSourceRead:
    """Register a new data source and trigger a background initial scan."""
    if body.kb_id != kb_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="kb_id mismatch",
        )
    _validate_connection_config(body.source_type, body.connection_config or {})
    try:
        table = await create_data_source(session, **body.model_dump())
    except Exception as e:
        log.error("create_source_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # Trigger initial scan in the background for enabled sources
    if table.enabled:
        # Mark as scanning immediately
        await update_data_source(session, table.id, scan_status="scanning")
        table = await get_data_source(session, table.id)  # type: ignore[assignment]

        source_id = table.id  # capture for closure
        background_tasks.add_task(_run_initial_scan, source_id)

    return _table_to_read(table)


async def _run_initial_scan(source_id: str) -> None:
    """Background task: run initial scan for a newly created data source."""
    from kb_curator.services.db import get_session_factory
    from kb_curator.services.polling import poll_data_source
    from kb_curator.services.change_classifier import get_change_classifier

    session_factory = get_session_factory()
    try:
        async with session_factory() as session:
            source = await get_data_source(session, source_id)
            if not source:
                return
            classifier = get_change_classifier()
            await poll_data_source(session, source, classifier, create_entries=True)
            await update_data_source(session, source_id, scan_status="completed")
    except Exception as e:
        log.error("background_initial_scan_failed", source_id=source_id, error=str(e))
        try:
            async with session_factory() as session:
                await update_data_source(session, source_id, scan_status="failed")
        except Exception:
            pass


@router.get("", response_model=list[DataSourceRead])
async def list_sources(
    kb_id: str,
    session: SessionDep,
    enabled_only: bool = Query(default=False),
) -> list[DataSourceRead]:
    """List data sources for a knowledge base."""
    sources = await list_data_sources(session=session, kb_id=kb_id, enabled_only=enabled_only)
    return [_table_to_read(s) for s in sources]


# ============================================================
# Fixed-path endpoints (MUST be before /{source_id} routes)
# ============================================================


@router.post("/poll")
async def poll_sources(
    kb_id: str,
    session: SessionDep,
) -> dict:
    """Manually trigger polling for all enabled data sources in a knowledge base.

    For each detected change, a knowledge entry is created and the knowledge
    extraction pipeline is run (chunking + embedding + KG extraction).
    """
    from kb_curator.services.polling import poll_data_source
    from kb_curator.services.change_classifier import get_change_classifier

    try:
        sources = await list_data_sources(session, kb_id=kb_id, enabled_only=True)
        if not sources:
            return {"kb_id": kb_id, "sources_polled": 0, "entries_created": 0, "errors": []}

        classifier = get_change_classifier()
        total_entries = 0
        all_errors: list[str] = []
        polled_count = 0

        for source in sources:
            try:
                changes = await poll_data_source(
                    session, source, classifier, create_entries=True,
                )
                polled_count += 1
                total_entries += len([
                    c for c in changes if (c.content_after or c.content_before)
                ])
            except Exception as e:
                all_errors.append(f"Source {source.id}: {str(e)}")

        return {
            "kb_id": kb_id,
            "sources_polled": polled_count,
            "entries_created": total_entries,
            "errors": all_errors,
        }
    except Exception as e:
        log.error("poll_sources_failed", kb_id=kb_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ============================================================
# Dynamic path endpoints
# ============================================================


@router.get("/{source_id}", response_model=DataSourceRead)
async def get_source(
    kb_id: str,
    source_id: str,
    session: SessionDep,
) -> DataSourceRead:
    """Get a specific data source."""
    source = await get_data_source(session, source_id)
    if not source or source.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")
    return _table_to_read(source)


@router.patch("/{source_id}", response_model=DataSourceRead)
async def update_source(
    kb_id: str,
    source_id: str,
    body: DataSourceUpdate,
    session: SessionDep = None,
) -> DataSourceRead:
    """Update a data source configuration."""
    source = await get_data_source(session, source_id)
    if not source or source.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

    updates: dict = body.model_dump(exclude_unset=True)
    if not updates:
        return _table_to_read(source)

    try:
        updated = await update_data_source(session, source_id, **updates)
        if not updated:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update data source")
        return _table_to_read(updated)
    except HTTPException:
        raise
    except Exception as e:
        log.error("update_source_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{source_id}", status_code=status.HTTP_200_OK)
async def delete_source(
    kb_id: str,
    source_id: str,
    session: SessionDep,
) -> dict:
    """Delete a data source."""
    source = await get_data_source(session, source_id)
    if not source or source.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")
    await delete_data_source(session, source_id)
    return {"status": "deleted", "source_id": source_id}


def _table_to_read(table) -> DataSourceRead:
    """Convert DataSourceTable to DataSourceRead."""
    config = table.connection_config
    if isinstance(config, str):
        config = json.loads(config)
    return DataSourceRead(
        id=table.id,
        kb_id=table.kb_id,
        name=table.name,
        source_type=table.source_type,
        connection_config=config,
        poll_interval_minutes=table.poll_interval_minutes,
        last_polled_at=table.last_polled_at,
        last_fingerprint=table.last_fingerprint,
        enabled=table.enabled,
        scan_status=getattr(table, "scan_status", "pending"),
        created_at=table.created_at,
    )
