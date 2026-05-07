"""API integration tests for Phase 4.8 routes.

Tests the full request/response cycle for:
- Knowledge entries CRUD + search
- Data source management
- Review tasks + decisions
- Knowledge graph queries
- Knowledge base management
- Token authentication
"""

import pytest
from httpx import ASGITransport, AsyncClient

from kb_curator.main import app


@pytest.fixture
async def client():
    """Async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


KB_ID = "test_kb_001"


# ============================================================
# Knowledge Entries CRUD
# ============================================================


class TestKnowledgeEntriesAPI:
    """Tests for /knowledge-bases/{kb_id}/entries endpoints."""

    @pytest.mark.asyncio
    async def test_create_entry(self, client: AsyncClient):
        response = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/entries",
            json={
                "kb_id": KB_ID,
                "title": "Test Entry",
                "content": "This is a test knowledge entry.",
                "source_id": "src_001",
                "tags": ["test"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Entry"
        assert data["kb_id"] == KB_ID
        assert data["version"] == 1
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_create_entry_kb_id_mismatch(self, client: AsyncClient):
        response = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/entries",
            json={
                "kb_id": "wrong_kb",
                "title": "Bad Entry",
                "content": "Content",
                "source_id": "src_001",
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_entries(self, client: AsyncClient):
        # Create some entries first
        for i in range(3):
            await client.post(
                f"/api/v1/knowledge-bases/{KB_ID}/entries",
                json={
                    "kb_id": KB_ID,
                    "title": f"Entry {i}",
                    "content": f"Content {i}",
                    "source_id": "src_001",
                },
            )
        response = await client.get(f"/api/v1/knowledge-bases/{KB_ID}/entries")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3

    @pytest.mark.asyncio
    async def test_get_entry(self, client: AsyncClient):
        # Create entry
        create_resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/entries",
            json={
                "kb_id": KB_ID,
                "title": "Get Test",
                "content": "Content",
                "source_id": "src_001",
            },
        )
        entry_id = create_resp.json()["id"]

        # Get entry
        response = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/entries/{entry_id}"
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Get Test"

    @pytest.mark.asyncio
    async def test_get_entry_not_found(self, client: AsyncClient):
        response = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/entries/nonexistent"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_entry(self, client: AsyncClient):
        # Create entry
        create_resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/entries",
            json={
                "kb_id": KB_ID,
                "title": "Original",
                "content": "Original content",
                "source_id": "src_001",
            },
        )
        entry_id = create_resp.json()["id"]

        # Update entry
        response = await client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/entries/{entry_id}",
            json={"title": "Updated Title"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_delete_entry(self, client: AsyncClient):
        # Create entry
        create_resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/entries",
            json={
                "kb_id": KB_ID,
                "title": "To Delete",
                "content": "Content",
                "source_id": "src_001",
            },
        )
        entry_id = create_resp.json()["id"]

        # Delete entry
        response = await client.delete(
            f"/api/v1/knowledge-bases/{KB_ID}/entries/{entry_id}"
        )
        assert response.status_code == 200

        # Verify deleted
        get_resp = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/entries/{entry_id}"
        )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_count_entries(self, client: AsyncClient):
        response = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/entries/count"
        )
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "kb_id" in data


# ============================================================
# Data Sources API
# ============================================================


class TestDataSourcesAPI:
    """Tests for /knowledge-bases/{kb_id}/sources endpoints."""

    @pytest.mark.asyncio
    async def test_create_source(self, client: AsyncClient):
        response = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/sources",
            json={
                "kb_id": KB_ID,
                "name": "Confluence Wiki",
                "source_type": "confluence",
                "connection_config": {"url": "https://wiki.example.com"},
                "poll_interval_minutes": 30,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Confluence Wiki"
        assert data["source_type"] == "confluence"

    @pytest.mark.asyncio
    async def test_list_sources(self, client: AsyncClient):
        response = await client.get(f"/api/v1/knowledge-bases/{KB_ID}/sources")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_get_source(self, client: AsyncClient):
        # Create source
        create_resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/sources",
            json={
                "kb_id": KB_ID,
                "name": "File Source",
                "source_type": "file",
                "connection_config": {"path": "/data/docs"},
            },
        )
        source_id = create_resp.json()["id"]

        # Get source
        response = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/sources/{source_id}"
        )
        assert response.status_code == 200
        assert response.json()["name"] == "File Source"

    @pytest.mark.asyncio
    async def test_update_source(self, client: AsyncClient):
        # Create source
        create_resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/sources",
            json={
                "kb_id": KB_ID,
                "name": "Old Name",
                "source_type": "file",
            },
        )
        source_id = create_resp.json()["id"]

        # Update source
        response = await client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/sources/{source_id}",
            json={"name": "New Name", "enabled": False},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_delete_source(self, client: AsyncClient):
        # Create source
        create_resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/sources",
            json={
                "kb_id": KB_ID,
                "name": "To Delete",
                "source_type": "file",
            },
        )
        source_id = create_resp.json()["id"]

        # Delete source
        response = await client.delete(
            f"/api/v1/knowledge-bases/{KB_ID}/sources/{source_id}"
        )
        assert response.status_code == 200


# ============================================================
# Review Tasks & Decisions API
# ============================================================


class TestReviewsAPI:
    """Tests for /knowledge-bases/{kb_id}/reviews endpoints."""

    @pytest.mark.asyncio
    async def test_create_review(self, client: AsyncClient):
        response = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews",
            params={
                "task_type": "conflict_resolution",
                "title": "Test Review",
                "description": "Please review this conflict",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Review"
        assert data["status"] == "pending"
        assert data["auto_resolve_at"] is not None

    @pytest.mark.asyncio
    async def test_list_reviews(self, client: AsyncClient):
        response = await client.get(f"/api/v1/knowledge-bases/{KB_ID}/reviews")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_get_review(self, client: AsyncClient):
        # Create review
        create_resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews",
            params={
                "task_type": "quality_action",
                "title": "Quality Issue",
                "description": "Low quality entry detected",
            },
        )
        task_id = create_resp.json()["id"]

        # Get review
        response = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}"
        )
        assert response.status_code == 200
        assert response.json()["task_type"] == "quality_action"

    @pytest.mark.asyncio
    async def test_submit_decision(self, client: AsyncClient):
        # Create review
        create_resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews",
            params={
                "task_type": "conflict_resolution",
                "title": "Decision Test",
                "description": "Test decision submission",
            },
        )
        task_id = create_resp.json()["id"]

        # Submit decision
        response = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}/decisions",
            json={
                "decision_type": "accept_new",
                "rationale": "New info is verified",
            },
            params={"decided_by": "admin"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["decision_type"] == "accept_new"
        assert data["decided_by"] == "admin"

    @pytest.mark.asyncio
    async def test_submit_decision_on_resolved_task(self, client: AsyncClient):
        # Create review
        create_resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews",
            params={
                "task_type": "conflict_resolution",
                "title": "Already Resolved",
                "description": "Test double decision",
            },
        )
        task_id = create_resp.json()["id"]

        # First decision
        await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}/decisions",
            json={
                "decision_type": "accept_new",
                "rationale": "First decision",
            },
            params={"decided_by": "admin"},
        )

        # Second decision should fail
        response = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}/decisions",
            json={
                "decision_type": "keep_old",
                "rationale": "Second decision",
            },
            params={"decided_by": "admin"},
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_list_decisions(self, client: AsyncClient):
        # Create review
        create_resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews",
            params={
                "task_type": "conflict_resolution",
                "title": "List Decisions Test",
                "description": "Test listing decisions",
            },
        )
        task_id = create_resp.json()["id"]

        # Submit decision
        await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}/decisions",
            json={
                "decision_type": "merge",
                "rationale": "Both have value",
                "merge_content": "Combined content",
            },
            params={"decided_by": "admin"},
        )

        # List decisions
        response = await client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}/decisions"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["decision_type"] == "merge"

    @pytest.mark.asyncio
    async def test_update_review_status(self, client: AsyncClient):
        # Create review
        create_resp = await client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews",
            params={
                "task_type": "conflict_resolution",
                "title": "Update Status Test",
                "description": "Test status update",
            },
        )
        task_id = create_resp.json()["id"]

        # Update to in_progress
        response = await client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/reviews/{task_id}",
            json={"task_status": "in_progress", "assigned_to": "reviewer1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"
        assert data["assigned_to"] == "reviewer1"


# ============================================================
# Knowledge Base Management API
# ============================================================


class TestKnowledgeBasesAPI:
    """Tests for /knowledge-bases endpoints."""

    @pytest.mark.asyncio
    async def test_list_knowledge_bases(self, client: AsyncClient):
        response = await client.get("/api/v1/knowledge-bases")
        assert response.status_code == 200
        data = response.json()
        assert "knowledge_bases" in data

    @pytest.mark.asyncio
    async def test_create_knowledge_base(self, client: AsyncClient):
        response = await client.post(f"/api/v1/knowledge-bases/{KB_ID}_new")
        assert response.status_code == 201
        data = response.json()
        assert data["kb_id"] == f"{KB_ID}_new"

    @pytest.mark.asyncio
    async def test_get_knowledge_base(self, client: AsyncClient):
        response = await client.get(f"/api/v1/knowledge-bases/{KB_ID}")
        assert response.status_code == 200
        data = response.json()
        assert data["kb_id"] == KB_ID
        assert "total_entries" in data
        assert "active_entries" in data


# ============================================================
# Authentication API
# ============================================================


class TestAuthAPI:
    """Tests for /auth endpoints."""

    @pytest.mark.asyncio
    async def test_token_endpoint_auth_disabled(self, client: AsyncClient):
        """When auth is disabled, token endpoint should return 400."""
        response = await client.post(
            "/api/v1/auth/token",
            json={"username": "admin", "password": "admin"},
        )
        # Auth is disabled by default in test settings
        assert response.status_code == 400
