"""Unit tests for SQLite CRUD operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kb_curator.models.db_tables import Base
from kb_curator.services.crud import (
    create_change_event,
    create_conflict,
    create_data_source,
    create_decision,
    create_entry,
    create_quality_report,
    create_review_task,
    get_entry,
    list_change_events,
    list_data_sources,
    list_decisions_for_task,
    list_entries,
    update_entry,
    count_entries,
    get_review_task,
    list_review_tasks,
    update_review_task,
    list_expired_review_tasks,
)


@pytest.fixture
async def db_session(tmp_path):
    """Create an in-memory SQLite session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


class TestKnowledgeEntryCRUD:
    @pytest.mark.asyncio
    async def test_create_entry(self, db_session):
        entry = await create_entry(
            db_session,
            kb_id="kb_001",
            title="退款政策",
            content="本公司产品支持7天无理由退款。",
            source_id="src_001",
            tags=["policy", "refund"],
        )
        assert entry.id is not None
        assert entry.kb_id == "kb_001"
        assert entry.title == "退款政策"
        assert entry.version == 1
        assert entry.status == "active"

    @pytest.mark.asyncio
    async def test_get_entry(self, db_session):
        created = await create_entry(
            db_session,
            kb_id="kb_001",
            title="Test",
            content="Content",
            source_id="src_001",
        )
        found = await get_entry(db_session, created.id)
        assert found is not None
        assert found.title == "Test"

    @pytest.mark.asyncio
    async def test_update_entry(self, db_session):
        created = await create_entry(
            db_session,
            kb_id="kb_001",
            title="Old Title",
            content="Old content",
            source_id="src_001",
        )
        updated = await update_entry(
            db_session,
            created.id,
            title="New Title",
            content="New content",
        )
        assert updated.title == "New Title"
        assert updated.content == "New content"
        assert updated.version == 2  # version incremented on content change

    @pytest.mark.asyncio
    async def test_list_entries(self, db_session):
        for i in range(3):
            await create_entry(
                db_session,
                kb_id="kb_001",
                title=f"Entry {i}",
                content=f"Content {i}",
                source_id="src_001",
            )
        entries = await list_entries(db_session, "kb_001")
        assert len(entries) == 3

    @pytest.mark.asyncio
    async def test_list_entries_filter_by_status(self, db_session):
        await create_entry(
            db_session, kb_id="kb_001", title="Active",
            content="c", source_id="src_001", status="active",
        )
        await create_entry(
            db_session, kb_id="kb_001", title="Archived",
            content="c", source_id="src_001", status="archived",
        )
        active = await list_entries(db_session, "kb_001", status="active")
        assert len(active) == 1
        assert active[0].title == "Active"

    @pytest.mark.asyncio
    async def test_count_entries(self, db_session):
        await create_entry(
            db_session, kb_id="kb_001", title="A",
            content="c", source_id="src_001",
        )
        await create_entry(
            db_session, kb_id="kb_001", title="B",
            content="c", source_id="src_001",
        )
        cnt = await count_entries(db_session, "kb_001")
        assert cnt == 2


class TestChangeEventCRUD:
    @pytest.mark.asyncio
    async def test_create_and_list(self, db_session):
        event = await create_change_event(
            db_session,
            kb_id="kb_001",
            source_id="src_001",
            change_type="policy_change",
            title="Policy Update",
            content_after="New policy text",
        )
        assert event.change_type == "policy_change"

        events = await list_change_events(db_session, "kb_001")
        assert len(events) == 1


class TestConflictCRUD:
    @pytest.mark.asyncio
    async def test_create_conflict(self, db_session):
        conflict = await create_conflict(
            db_session,
            kb_id="kb_001",
            change_event_id="evt_001",
            conflict_type="semantic",
            new_content="New",
            existing_content="Old",
            summary="Contradiction detected",
            severity="high",
        )
        assert conflict.conflict_type == "semantic"
        assert conflict.severity == "high"


class TestReviewTaskCRUD:
    @pytest.mark.asyncio
    async def test_create_and_update(self, db_session):
        from datetime import datetime, timedelta

        task = await create_review_task(
            db_session,
            kb_id="kb_001",
            task_type="conflict_resolution",
            title="Review needed",
            description="Please review this conflict",
            auto_resolve_at=datetime.utcnow() + timedelta(hours=24),
        )
        assert task.status == "pending"

        updated = await update_review_task(
            db_session, task.id, status="resolved"
        )
        assert updated.status == "resolved"

    @pytest.mark.asyncio
    async def test_expired_tasks(self, db_session):
        from datetime import datetime, timedelta

        # Create an expired task
        await create_review_task(
            db_session,
            kb_id="kb_001",
            task_type="conflict_resolution",
            title="Expired task",
            description="Should be auto-resolved",
            auto_resolve_at=datetime.utcnow() - timedelta(hours=1),
        )
        # Create a non-expired task
        await create_review_task(
            db_session,
            kb_id="kb_001",
            task_type="conflict_resolution",
            title="Still pending",
            description="Not yet expired",
            auto_resolve_at=datetime.utcnow() + timedelta(hours=1),
        )

        expired = await list_expired_review_tasks(db_session)
        assert len(expired) == 1
        assert expired[0].title == "Expired task"


class TestDecisionCRUD:
    @pytest.mark.asyncio
    async def test_create_decision(self, db_session):
        decision = await create_decision(
            db_session,
            review_task_id="task_001",
            decision_type="accept_new",
            rationale="New policy is valid",
            decided_by="user_001",
        )
        assert decision.decision_type == "accept_new"

        decisions = await list_decisions_for_task(db_session, "task_001")
        assert len(decisions) == 1


class TestDataSourceCRUD:
    @pytest.mark.asyncio
    async def test_create_and_list(self, db_session):
        source = await create_data_source(
            db_session,
            kb_id="kb_001",
            name="Confluence",
            source_type="confluence",
            connection_config={"url": "https://wiki.example.com"},
        )
        assert source.source_type == "confluence"

        sources = await list_data_sources(db_session, "kb_001")
        assert len(sources) == 1


class TestQualityReportCRUD:
    @pytest.mark.asyncio
    async def test_create_report(self, db_session):
        report = await create_quality_report(
            db_session,
            kb_id="kb_001",
            inspection_type="incremental",
            total_entries=10,
            score=85.5,
            issues=[{"entry_id": "e1", "issue_type": "expired"}],
        )
        assert report.score == 85.5
        assert report.total_entries == 10
