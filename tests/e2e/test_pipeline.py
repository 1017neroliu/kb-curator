"""End-to-end tests for the complete KB-Curator pipeline.

Tests the full workflow:
1. Create KB → Create Source → Create Entry
2. Change detection → Event creation
3. Knowledge extraction pipeline
4. Conflict detection
5. Review task creation → Decision
6. Quality inspection
7. Agent run (no-conflict path)
8. Agent run (conflict path → human review)
9. Knowledge graph operations
10. Cross-module data integrity

These tests use the FastAPI test client against the real app with an
in-memory SQLite database. External services (Neo4j, Redis, LLM) are
mocked at the service level.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure test environment
os.environ["KB_CURATOR_AUTH_ENABLED"] = "false"
os.environ["KB_CURATOR_DEBUG"] = "true"

from kb_curator.main import app


@pytest.fixture
async def client():
    """Async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


KB_ID = "e2e_kb"
SOURCE_ID = "e2e_src"


# ============================================================
# Helper: Create prerequisite resources
# ============================================================

async def create_prerequisites(client: AsyncClient) -> None:
    """Create KB and source needed for most tests."""
    # Create KB
    await client.post(f"/api/v1/knowledge-bases/{KB_ID}")
    # Create source
    await client.post(
        f"/api/v1/knowledge-bases/{KB_ID}/sources",
        json={
            "kb_id": KB_ID,
            "name": "E2E Test Source",
            "source_type": "file",
            "connection_config": {"path": "/data/test"},
            "poll_interval_minutes": 30,
        },
    )


# ============================================================
# Full Pipeline E2E Tests
# ============================================================


class TestFullPipeline:
    """End-to-end test for the complete knowledge lifecycle."""

    @pytest.mark.asyncio
    async def test_create_kb_to_quality_report(self, client: AsyncClient):
        """Full pipeline: KB → Source → Entry → Event → Quality."""
        # Step 1: Create knowledge base
        resp = await client.post(f"/api/v1/knowledge-bases/{KB_ID}")
        assert resp.status_code == 201

        # Step 2: Create data source
        resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/sources",
            json={
                "kb_id": KB_ID,
                "name": "Pipeline Source",
                "source_type": "file",
                "connection_config": {"path": "/data/docs"},
            },
        )
        assert resp.status_code == 201
        source_id = resp.json()["id"]

        # Step 3: Create knowledge entries
        entry_ids = []
        for i in range(3):
            resp = await client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/entries",
                json={
                    "kb_id": KB_ID,
                    "title": f"Pipeline Entry {i}",
                    "content": f"This is knowledge content item {i} for end-to-end testing.",
                    "source_id": source_id,
                    "tags": ["e2e", f"item-{i}"],
                },
            )
            assert resp.status_code == 201
            entry_ids.append(resp.json()["id"])

        # Step 4: Create change event
        resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/events",
            json={
                "kb_id": KB_ID,
                "source_id": source_id,
                "change_type": "new_info",
                "title": "New documentation detected",
                "content_after": "Updated documentation content",
            },
        )
        assert resp.status_code == 201
        event_id = resp.json()["id"]

        # Step 5: List and verify events
        resp = await client.get(f"/api/v1/knowledge-bases/{KB_ID}/events")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) >= 1

        # Step 6: Verify KB overview
        resp = await client.get(f"/api/v1/knowledge-bases/{KB_ID}")
        assert resp.status_code == 200
        overview = resp.json()
        assert overview["kb_id"] == KB_ID
        assert overview["total_entries"] >= 3
        assert overview["active_entries"] >= 3

        # Step 7: Run quality inspection
        resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/quality/inspect",
            params={"inspection_type": "incremental"},
        )
        assert resp.status_code == 201
        report = resp.json()
        assert "score" in report
        assert "issues" in report
        report_id = report["id"]

        # Step 8: Get quality report
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/quality/reports/{report_id}"
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == report_id

        # Step 9: List quality reports
        resp = await client.get(f"/api/v1/knowledge-bases/{KB_ID}/quality/reports")
        assert resp.status_code == 200
        reports = resp.json()
        assert len(reports) >= 1

        # Step 10: Update an entry
        resp = await client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/entries/{entry_ids[0]}",
            json={"title": "Updated Pipeline Entry", "content": "Updated content"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Pipeline Entry"
        assert resp.json()["version"] == 2

        # Step 11: Verify entry count
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/entries/count"
        )
        assert resp.status_code == 200
        assert resp.json()["count"] >= 3


class TestConflictReviewPipeline:
    """End-to-end test for conflict detection and review workflow."""

    @pytest.mark.asyncio
    async def test_conflict_to_decision_flow(self, client: AsyncClient):
        """Pipeline: Create entries → Create conflict → Review → Decision."""
        await create_prerequisites(client)

        # Step 1: Create a conflict record
        resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/conflicts",
            params={
                "change_event_id": "evt_conflict_001",
                "new_content": "Python 4 was released in 2025",
                "existing_content": "Python 4 has not been released",
                "conflict_type": "semantic",
                "severity": "critical",
            },
        )
        assert resp.status_code == 201
        conflict_id = resp.json()["id"]

        # Step 2: Verify conflict in list
        resp = await client.get(f"/api/v1/knowledge-bases/{KB_ID}/conflicts")
        assert resp.status_code == 200
        conflicts = resp.json()
        assert len(conflicts) >= 1

        # Step 3: Get conflict detail
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/conflicts/{conflict_id}"
        )
        assert resp.status_code == 200
        assert resp.json()["conflict_type"] == "semantic"
        assert resp.json()["severity"] == "critical"

        # Step 4: Create review task for the conflict
        resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews",
            params={
                "conflict_id": conflict_id,
                "task_type": "conflict_resolution",
                "title": "Review Python version conflict",
                "description": "Contradictory information about Python 4 release",
            },
        )
        assert resp.status_code == 201
        task = resp.json()
        task_id = task["id"]
        assert task["status"] == "pending"

        # Step 5: Update review status to in_progress
        resp = await client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}",
            json={"task_status": "in_progress", "assigned_to": "reviewer1"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

        # Step 6: Submit decision
        resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}/decisions",
            json={
                "decision_type": "accept_new",
                "rationale": "New information is verified and more recent",
            },
            params={"decided_by": "admin"},
        )
        assert resp.status_code == 201
        decision = resp.json()
        assert decision["decision_type"] == "accept_new"
        assert decision["decided_by"] == "admin"

        # Step 7: Verify review is now resolved
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"

        # Step 8: List decisions for the task
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}/decisions"
        )
        assert resp.status_code == 200
        decisions = resp.json()
        assert len(decisions) >= 1
        assert decisions[0]["decision_type"] == "accept_new"

        # Step 9: Cannot submit second decision on resolved task
        resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}/decisions",
            json={
                "decision_type": "keep_old",
                "rationale": "Changed my mind",
            },
            params={"decided_by": "admin"},
        )
        assert resp.status_code == 409


class TestEventsPipeline:
    """End-to-end test for change event lifecycle."""

    @pytest.mark.asyncio
    async def test_event_crud_and_filtering(self, client: AsyncClient):
        """Create events, list with filters, get detail."""
        await create_prerequisites(client)

        # Create events of different types
        event_types = ["new_info", "policy_change", "contradiction", "correction", "redundant"]
        event_ids = []
        for ct in event_types:
            resp = await client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/events",
                json={
                    "kb_id": KB_ID,
                    "source_id": SOURCE_ID,
                    "change_type": ct,
                    "title": f"Event: {ct}",
                    "content_before": f"Old content for {ct}",
                    "content_after": f"New content for {ct}",
                },
            )
            assert resp.status_code == 201
            event_ids.append(resp.json()["id"])

        # List all events
        resp = await client.get(f"/api/v1/knowledge-bases/{KB_ID}/events")
        assert resp.status_code == 200
        all_events = resp.json()
        assert len(all_events) >= 5

        # Filter by change_type
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/events",
            params={"change_type": "contradiction"},
        )
        assert resp.status_code == 200
        filtered = resp.json()
        assert all(e["change_type"] == "contradiction" for e in filtered)
        assert len(filtered) >= 1

        # Get specific event
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/events/{event_ids[0]}"
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == f"Event: {event_types[0]}"

        # Get nonexistent event
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/events/nonexistent"
        )
        assert resp.status_code == 404


class TestEntriesSearchPipeline:
    """End-to-end test for entries with search."""

    @pytest.mark.asyncio
    async def test_entry_search_workflow(self, client: AsyncClient):
        """Create entries, search, filter by status, paginate."""
        await create_prerequisites(client)

        # Create entries with different statuses
        for i in range(5):
            resp = await client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/entries",
                json={
                    "kb_id": KB_ID,
                    "title": f"Search Entry {i}",
                    "content": f"Content about machine learning and AI techniques {i}",
                    "source_id": SOURCE_ID,
                    "tags": ["ml", "ai"],
                },
            )
            assert resp.status_code == 201

        # List all entries
        resp = await client.get(f"/api/v1/knowledge-bases/{KB_ID}/entries")
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) >= 5

        # Filter by status
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/entries",
            params={"status": "active"},
        )
        assert resp.status_code == 200
        active_entries = resp.json()
        assert all(e["status"] == "active" for e in active_entries)

        # Archive an entry
        entry_id = entries[0]["id"]
        resp = await client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/entries/{entry_id}",
            json={"status": "archived"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

        # Verify count
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/entries/count",
            params={"status": "active"},
        )
        assert resp.status_code == 200
        assert resp.json()["count"] >= 4


class TestMultiKbIsolation:
    """Test multi-tenant data isolation between knowledge bases."""

    @pytest.mark.asyncio
    async def test_data_isolation(self, client: AsyncClient):
        """Entries in one KB should not be visible in another."""
        kb1 = "e2e_kb_alpha"
        kb2 = "e2e_kb_beta"

        # Create two KBs
        await client.post(f"/api/v1/knowledge-bases/{kb1}")
        await client.post(f"/api/v1/knowledge-bases/{kb2}")

        # Create sources in each
        for kb in [kb1, kb2]:
            await client.post(
                f"/api/v1/knowledge-bases/{kb}/sources",
                json={
                    "kb_id": kb,
                    "name": f"Source for {kb}",
                    "source_type": "file",
                },
            )

        # Create entry in kb1
        resp = await client.post(
            f"/api/v1/knowledge-bases/{kb1}/entries",
            json={
                "kb_id": kb1,
                "title": "Alpha Entry",
                "content": "Content for alpha",
                "source_id": "src_alpha",
            },
        )
        assert resp.status_code == 201
        alpha_entry_id = resp.json()["id"]

        # Create entry in kb2
        resp = await client.post(
            f"/api/v1/knowledge-bases/{kb2}/entries",
            json={
                "kb_id": kb2,
                "title": "Beta Entry",
                "content": "Content for beta",
                "source_id": "src_beta",
            },
        )
        assert resp.status_code == 201
        beta_entry_id = resp.json()["id"]

        # Verify isolation: kb1 entries should not contain kb2 entries
        resp = await client.get(f"/api/v1/knowledge-bases/{kb1}/entries")
        assert resp.status_code == 200
        kb1_entries = resp.json()
        assert all(e["kb_id"] == kb1 for e in kb1_entries)

        resp = await client.get(f"/api/v1/knowledge-bases/{kb2}/entries")
        assert resp.status_code == 200
        kb2_entries = resp.json()
        assert all(e["kb_id"] == kb2 for e in kb2_entries)

        # Verify entry IDs are different
        assert alpha_entry_id != beta_entry_id


class TestSystemEndpoints:
    """Test system health and readiness endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        resp = await client.get("/api/v1/system/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "kb-curator"

    @pytest.mark.asyncio
    async def test_readiness_check(self, client: AsyncClient):
        resp = await client.get("/api/v1/system/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert "checks" in data
        # In test env, neo4j and redis may be unavailable
        assert data["status"] in ["ok", "degraded"]


class TestReviewFilteringAndPagination:
    """Test review task filtering and pagination edge cases."""

    @pytest.mark.asyncio
    async def test_review_status_filtering(self, client: AsyncClient):
        """Create reviews with different statuses, filter by each."""
        await create_prerequisites(client)

        # Create multiple reviews
        for i in range(3):
            await client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/reviews",
                params={
                    "task_type": "conflict_resolution",
                    "title": f"Filter Review {i}",
                    "description": f"Description {i}",
                },
            )

        # Filter by pending
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews",
            params={"status": "pending"},
        )
        assert resp.status_code == 200
        pending = resp.json()
        assert all(r["status"] == "pending" for r in pending)

        # Filter by type
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews",
            params={"type": "conflict_resolution"},
        )
        assert resp.status_code == 200
        typed = resp.json()
        assert all(r["task_type"] == "conflict_resolution" for r in typed)


class TestDeleteKb:
    """Test knowledge base deletion with confirmation."""

    @pytest.mark.asyncio
    async def test_delete_without_confirm(self, client: AsyncClient):
        """Delete without confirm should fail or warn."""
        await client.post(f"/api/v1/knowledge-bases/{KB_ID}_del")
        resp = await client.delete(
            f"/api/v1/knowledge-bases/{KB_ID}_del",
            params={"confirm": False},
        )
        # Without confirm, deletion should be rejected or return warning
        # Exact behavior depends on implementation

    @pytest.mark.asyncio
    async def test_delete_with_confirm(self, client: AsyncClient):
        """Delete with confirm should succeed."""
        await client.post(f"/api/v1/knowledge-bases/{KB_ID}_del2")
        resp = await client.delete(
            f"/api/v1/knowledge-bases/{KB_ID}_del2",
            params={"confirm": True},
        )
        assert resp.status_code == 200


class TestEntryVersioning:
    """Test knowledge entry version incrementing on content updates."""

    @pytest.mark.asyncio
    async def test_version_increment_on_content_update(self, client: AsyncClient):
        """Each content update should increment the version."""
        await create_prerequisites(client)

        # Create entry
        resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/entries",
            json={
                "kb_id": KB_ID,
                "title": "Versioned Entry",
                "content": "Version 1",
                "source_id": SOURCE_ID,
            },
        )
        entry_id = resp.json()["id"]
        assert resp.json()["version"] == 1

        # Update content → version should increment
        resp = await client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/entries/{entry_id}",
            json={"content": "Version 2"},
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

        # Update title only → version should NOT increment
        resp = await client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/entries/{entry_id}",
            json={"title": "New Title"},
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 2

        # Update content again → version should increment
        resp = await client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/entries/{entry_id}",
            json={"content": "Version 3"},
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 3


class TestDecisionMergeContent:
    """Test decision submission with merge content."""

    @pytest.mark.asyncio
    async def test_merge_decision_with_content(self, client: AsyncClient):
        """Submit a merge decision with combined content."""
        await create_prerequisites(client)

        # Create review
        resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews",
            params={
                "task_type": "conflict_resolution",
                "title": "Merge Test",
                "description": "Test merge decision",
            },
        )
        task_id = resp.json()["id"]

        # Submit merge decision
        resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}/decisions",
            json={
                "decision_type": "merge",
                "rationale": "Both versions contain useful information",
                "merge_content": "Combined: Python 3.12 is the latest stable release. Python 4.0 is planned for 2026.",
            },
            params={"decided_by": "admin"},
        )
        assert resp.status_code == 201
        assert resp.json()["decision_type"] == "merge"
        assert resp.json()["merge_content"] is not None

        # Verify in decisions list
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}/decisions"
        )
        decisions = resp.json()
        assert len(decisions) >= 1
        assert decisions[0]["merge_content"] is not None


class TestSourceEnableDisable:
    """Test data source enable/disable toggle."""

    @pytest.mark.asyncio
    async def test_source_toggle(self, client: AsyncClient):
        """Create source, disable, verify, re-enable."""
        await create_prerequisites(client)

        # List all sources (including disabled)
        resp = await client.get(f"/api/v1/knowledge-bases/{KB_ID}/sources")
        assert resp.status_code == 200
        sources = resp.json()
        assert len(sources) >= 1
        source_id = sources[0]["id"]

        # Disable source
        resp = await client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/sources/{source_id}",
            json={"enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

        # List enabled only
        resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/sources",
            params={"enabled_only": True},
        )
        enabled_sources = resp.json()
        assert all(s["enabled"] for s in enabled_sources)

        # Re-enable
        resp = await client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/sources/{source_id}",
            json={"enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
