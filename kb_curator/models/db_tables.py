"""SQLAlchemy table definitions for the metadata database."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class KnowledgeEntryTable(Base):
    """Knowledge entries stored in SQLite for metadata tracking."""

    __tablename__ = "knowledge_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    tags: Mapped[str] = mapped_column(Text, default="[]")  # JSON array string
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class ChangeEventTable(Base):
    """Change events detected from document sources."""

    __tablename__ = "change_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    change_type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(512))
    content_before: Mapped[str | None] = mapped_column(Text)
    content_after: Mapped[str | None] = mapped_column(Text)
    fingerprint_before: Mapped[str | None] = mapped_column(String(128))
    fingerprint_after: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class ConflictTable(Base):
    """Detected conflicts between new and existing knowledge."""

    __tablename__ = "conflicts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    change_event_id: Mapped[str] = mapped_column(String(64), index=True)
    conflict_type: Mapped[str] = mapped_column(String(32))
    existing_entry_id: Mapped[str | None] = mapped_column(String(64))
    existing_entity_id: Mapped[str | None] = mapped_column(String(64))
    new_content: Mapped[str] = mapped_column(Text)
    existing_content: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class ReviewTaskTable(Base):
    """Human review tasks for conflict resolution and quality actions."""

    __tablename__ = "review_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    conflict_id: Mapped[str | None] = mapped_column(String(64))
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(128))
    auto_resolve_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)


class DecisionTable(Base):
    """Human decisions on review tasks."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    review_task_id: Mapped[str] = mapped_column(String(64), index=True)
    decision_type: Mapped[str] = mapped_column(String(32))
    rationale: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(String(128))
    merge_content: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class DataSourceTable(Base):
    """Registered document sources for change detection."""

    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(256))
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    connection_config: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_fingerprint: Mapped[str | None] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class QualityReportTable(Base):
    """Quality inspection reports."""

    __tablename__ = "quality_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    inspection_type: Mapped[str] = mapped_column(String(32))
    total_entries: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(default=0.0)
    issues_json: Mapped[str] = mapped_column(Text, default="[]")  # JSON array
    inspected_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
