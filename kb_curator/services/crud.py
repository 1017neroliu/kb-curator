"""CRUD operations for the SQLite metadata database."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Sequence
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kb_curator.core.logging import get_logger
from kb_curator.models.db_tables import (
    ChangeEventTable,
    ConflictTable,
    DataSourceTable,
    DecisionTable,
    KnowledgeEntryTable,
    QualityReportTable,
    ReviewTaskTable,
)
from kb_curator.models.schemas import (
    ChangeType,
    ConflictType,
    DecisionType,
    EntryStatus,
    ReviewTaskStatus,
    ReviewTaskType,
    Severity,
)

log = get_logger(__name__)


# ============================================================
# Knowledge Entry
# ============================================================

async def create_entry(session: AsyncSession, **kwargs: Any) -> KnowledgeEntryTable:
    """Create a new knowledge entry."""
    entry = KnowledgeEntryTable(
        id=kwargs.get("id", uuid4().hex),
        kb_id=kwargs["kb_id"],
        title=kwargs["title"],
        content=kwargs["content"],
        source_id=kwargs["source_id"],
        source_url=kwargs.get("source_url"),
        version=kwargs.get("version", 1),
        status=kwargs.get("status", "active"),
        tags=json.dumps(kwargs.get("tags", [])),
        expires_at=kwargs.get("expires_at"),
        metadata_json=json.dumps(kwargs.get("metadata", {})),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    log.info("entry_created", entry_id=entry.id, kb_id=entry.kb_id)
    return entry


async def get_entry(session: AsyncSession, entry_id: str) -> KnowledgeEntryTable | None:
    """Get a knowledge entry by ID."""
    result = await session.execute(
        select(KnowledgeEntryTable).where(KnowledgeEntryTable.id == entry_id)
    )
    return result.scalar_one_or_none()


async def list_entries(
    session: AsyncSession,
    kb_id: str,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[KnowledgeEntryTable]:
    """List knowledge entries for a KB, optionally filtered by status."""
    stmt = select(KnowledgeEntryTable).where(KnowledgeEntryTable.kb_id == kb_id)
    if status:
        stmt = stmt.where(KnowledgeEntryTable.status == status)
    stmt = stmt.order_by(KnowledgeEntryTable.updated_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_entry(session: AsyncSession, entry_id: str, **kwargs: Any) -> KnowledgeEntryTable | None:
    """Update a knowledge entry."""
    entry = await get_entry(session, entry_id)
    if not entry:
        return None

    for key, value in kwargs.items():
        if key == "tags":
            setattr(entry, key, json.dumps(value))
        elif key == "metadata":
            setattr(entry, "metadata_json", json.dumps(value))
        elif hasattr(entry, key):
            setattr(entry, key, value)

    entry.updated_at = datetime.utcnow()
    if "content" in kwargs:
        entry.version = (entry.version or 0) + 1

    await session.commit()
    await session.refresh(entry)
    log.info("entry_updated", entry_id=entry_id, version=entry.version)
    return entry


async def delete_entry(session: AsyncSession, entry_id: str) -> bool:
    """Delete a knowledge entry."""
    await session.execute(
        delete(KnowledgeEntryTable).where(KnowledgeEntryTable.id == entry_id)
    )
    await session.commit()
    log.info("entry_deleted", entry_id=entry_id)
    return True


async def count_entries(session: AsyncSession, kb_id: str, status: str | None = None) -> int:
    """Count knowledge entries for a KB."""
    from sqlalchemy import func
    stmt = select(func.count()).select_from(KnowledgeEntryTable).where(
        KnowledgeEntryTable.kb_id == kb_id
    )
    if status:
        stmt = stmt.where(KnowledgeEntryTable.status == status)
    result = await session.execute(stmt)
    return result.scalar() or 0


# ============================================================
# Change Event
# ============================================================

async def create_change_event(session: AsyncSession, **kwargs: Any) -> ChangeEventTable:
    """Create a new change event."""
    event = ChangeEventTable(
        id=kwargs.get("id", uuid4().hex),
        kb_id=kwargs["kb_id"],
        source_id=kwargs["source_id"],
        change_type=kwargs.get("change_type", "new_info"),
        title=kwargs["title"],
        content_before=kwargs.get("content_before"),
        content_after=kwargs.get("content_after"),
        fingerprint_before=kwargs.get("fingerprint_before"),
        fingerprint_after=kwargs.get("fingerprint_after"),
        metadata_json=json.dumps(kwargs.get("metadata", {})),
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    log.info("change_event_created", event_id=event.id, kb_id=event.kb_id)
    return event


async def get_change_event(session: AsyncSession, event_id: str) -> ChangeEventTable | None:
    """Get a change event by ID."""
    result = await session.execute(
        select(ChangeEventTable).where(ChangeEventTable.id == event_id)
    )
    return result.scalar_one_or_none()


async def list_change_events(
    session: AsyncSession,
    kb_id: str,
    change_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[ChangeEventTable]:
    """List change events for a KB."""
    stmt = select(ChangeEventTable).where(ChangeEventTable.kb_id == kb_id)
    if change_type:
        stmt = stmt.where(ChangeEventTable.change_type == change_type)
    stmt = stmt.order_by(ChangeEventTable.detected_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()


# ============================================================
# Conflict
# ============================================================

async def create_conflict(session: AsyncSession, **kwargs: Any) -> ConflictTable:
    """Create a new conflict record."""
    conflict = ConflictTable(
        id=kwargs.get("id", uuid4().hex),
        kb_id=kwargs["kb_id"],
        change_event_id=kwargs["change_event_id"],
        conflict_type=kwargs.get("conflict_type", "semantic"),
        existing_entry_id=kwargs.get("existing_entry_id"),
        existing_entity_id=kwargs.get("existing_entity_id"),
        new_content=kwargs["new_content"],
        existing_content=kwargs["existing_content"],
        summary=kwargs["summary"],
        severity=kwargs.get("severity", "warning"),
    )
    session.add(conflict)
    await session.commit()
    await session.refresh(conflict)
    log.info("conflict_created", conflict_id=conflict.id, kb_id=conflict.kb_id)
    return conflict


async def get_conflict(session: AsyncSession, conflict_id: str) -> ConflictTable | None:
    """Get a conflict by ID."""
    result = await session.execute(
        select(ConflictTable).where(ConflictTable.id == conflict_id)
    )
    return result.scalar_one_or_none()


async def list_conflicts(
    session: AsyncSession,
    kb_id: str,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[ConflictTable]:
    """List conflicts for a KB."""
    stmt = (
        select(ConflictTable)
        .where(ConflictTable.kb_id == kb_id)
        .order_by(ConflictTable.detected_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


# ============================================================
# Review Task
# ============================================================

async def create_review_task(session: AsyncSession, **kwargs: Any) -> ReviewTaskTable:
    """Create a new review task."""
    task = ReviewTaskTable(
        id=kwargs.get("id", uuid4().hex),
        kb_id=kwargs["kb_id"],
        conflict_id=kwargs.get("conflict_id"),
        task_type=kwargs.get("task_type", "conflict_resolution"),
        title=kwargs["title"],
        description=kwargs["description"],
        status=kwargs.get("status", "pending"),
        assigned_to=kwargs.get("assigned_to"),
        auto_resolve_at=kwargs.get("auto_resolve_at"),
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    log.info("review_task_created", task_id=task.id, kb_id=task.kb_id, task_type=task.task_type)
    return task


async def get_review_task(session: AsyncSession, task_id: str) -> ReviewTaskTable | None:
    """Get a review task by ID."""
    result = await session.execute(
        select(ReviewTaskTable).where(ReviewTaskTable.id == task_id)
    )
    return result.scalar_one_or_none()


async def list_review_tasks(
    session: AsyncSession,
    kb_id: str,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[ReviewTaskTable]:
    """List review tasks for a KB, optionally filtered by status."""
    stmt = select(ReviewTaskTable).where(ReviewTaskTable.kb_id == kb_id)
    if status:
        stmt = stmt.where(ReviewTaskTable.status == status)
    stmt = stmt.order_by(ReviewTaskTable.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_review_task(session: AsyncSession, task_id: str, **kwargs: Any) -> ReviewTaskTable | None:
    """Update a review task."""
    task = await get_review_task(session, task_id)
    if not task:
        return None
    for key, value in kwargs.items():
        if hasattr(task, key):
            setattr(task, key, value)
    await session.commit()
    await session.refresh(task)
    log.info("review_task_updated", task_id=task_id, updates=list(kwargs.keys()))
    return task


async def list_expired_review_tasks(session: AsyncSession, now: datetime | None = None) -> Sequence[ReviewTaskTable]:
    """Find review tasks that have exceeded their auto_resolve_at time."""
    now = now or datetime.utcnow()
    stmt = (
        select(ReviewTaskTable)
        .where(ReviewTaskTable.status == "pending")
        .where(ReviewTaskTable.auto_resolve_at <= now)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


# ============================================================
# Decision
# ============================================================

async def create_decision(session: AsyncSession, **kwargs: Any) -> DecisionTable:
    """Create a new decision record."""
    decision = DecisionTable(
        id=kwargs.get("id", uuid4().hex),
        review_task_id=kwargs["review_task_id"],
        decision_type=kwargs["decision_type"],
        rationale=kwargs["rationale"],
        decided_by=kwargs["decided_by"],
        merge_content=kwargs.get("merge_content"),
    )
    session.add(decision)
    await session.commit()
    await session.refresh(decision)
    log.info("decision_created", decision_id=decision.id,
             task_id=decision.review_task_id, decision_type=decision.decision_type)
    return decision


async def list_decisions_for_task(session: AsyncSession, task_id: str) -> Sequence[DecisionTable]:
    """List all decisions for a review task."""
    stmt = (
        select(DecisionTable)
        .where(DecisionTable.review_task_id == task_id)
        .order_by(DecisionTable.decided_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


# ============================================================
# Data Source
# ============================================================

async def create_data_source(session: AsyncSession, **kwargs: Any) -> DataSourceTable:
    """Create a new data source."""
    source = DataSourceTable(
        id=kwargs.get("id", uuid4().hex),
        kb_id=kwargs["kb_id"],
        name=kwargs["name"],
        source_type=kwargs["source_type"],
        connection_config=json.dumps(kwargs.get("connection_config", {})),
        poll_interval_minutes=kwargs.get("poll_interval_minutes", 60),
        enabled=kwargs.get("enabled", True),
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    log.info("data_source_created", source_id=source.id, kb_id=source.kb_id,
             source_type=source.source_type)
    return source


async def get_data_source(session: AsyncSession, source_id: str) -> DataSourceTable | None:
    """Get a data source by ID."""
    result = await session.execute(
        select(DataSourceTable).where(DataSourceTable.id == source_id)
    )
    return result.scalar_one_or_none()


async def list_data_sources(
    session: AsyncSession,
    kb_id: str | None = None,
    enabled_only: bool = False,
) -> Sequence[DataSourceTable]:
    """List data sources, optionally filtered by KB."""
    stmt = select(DataSourceTable)
    if kb_id:
        stmt = stmt.where(DataSourceTable.kb_id == kb_id)
    if enabled_only:
        stmt = stmt.where(DataSourceTable.enabled == True)  # noqa: E712
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_data_source(session: AsyncSession, source_id: str, **kwargs: Any) -> DataSourceTable | None:
    """Update a data source."""
    source = await get_data_source(session, source_id)
    if not source:
        return None
    for key, value in kwargs.items():
        if key == "connection_config":
            setattr(source, key, json.dumps(value))
        elif hasattr(source, key):
            setattr(source, key, value)
    source.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(source)
    log.info("data_source_updated", source_id=source_id)
    return source


async def delete_data_source(session: AsyncSession, source_id: str) -> bool:
    """Delete a data source."""
    await session.execute(
        delete(DataSourceTable).where(DataSourceTable.id == source_id)
    )
    await session.commit()
    log.info("data_source_deleted", source_id=source_id)
    return True


# ============================================================
# Quality Report
# ============================================================

async def create_quality_report(session: AsyncSession, **kwargs: Any) -> QualityReportTable:
    """Create a new quality report."""
    report = QualityReportTable(
        id=kwargs.get("id", uuid4().hex),
        kb_id=kwargs["kb_id"],
        inspection_type=kwargs.get("inspection_type", "incremental"),
        total_entries=kwargs.get("total_entries", 0),
        score=kwargs.get("score", 0.0),
        issues_json=json.dumps(kwargs.get("issues", [])),
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    log.info("quality_report_created", report_id=report.id,
             kb_id=report.kb_id, score=report.score)
    return report


async def get_quality_report(session: AsyncSession, report_id: str) -> QualityReportTable | None:
    """Get a quality report by ID."""
    result = await session.execute(
        select(QualityReportTable).where(QualityReportTable.id == report_id)
    )
    return result.scalar_one_or_none()


async def list_quality_reports(
    session: AsyncSession,
    kb_id: str,
    limit: int = 20,
    offset: int = 0,
) -> Sequence[QualityReportTable]:
    """List quality reports for a KB."""
    stmt = (
        select(QualityReportTable)
        .where(QualityReportTable.kb_id == kb_id)
        .order_by(QualityReportTable.inspected_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()
