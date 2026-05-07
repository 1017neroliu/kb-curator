"""Unit tests for knowledge updater module."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from kb_curator.models.schemas import UpdateOperation, UpdatePlan, UpdateStrategy
from kb_curator.services.knowledge_updater import (
    KnowledgeUpdater,
    UpdateResult,
    UpdateStatus,
)


class TestUpdateResult:
    """Test cases for UpdateResult."""

    def test_success_result(self) -> None:
        """Test successful result."""
        result = UpdateResult(
            success=True,
            status=UpdateStatus.COMPLETED,
            operations_completed=3,
        )
        assert result.success is True
        assert result.status == UpdateStatus.COMPLETED
        assert result.operations_completed == 3

    def test_failed_result(self) -> None:
        """Test failed result."""
        result = UpdateResult(
            success=False,
            status=UpdateStatus.FAILED,
            operations_completed=2,
            operations_failed=1,
            errors=["Operation failed"],
        )
        assert result.success is False
        assert result.status == UpdateStatus.FAILED
        assert len(result.errors) == 1


class TestUpdateStatus:
    """Test cases for UpdateStatus enum."""

    def test_all_statuses(self) -> None:
        """Test all update statuses are defined."""
        assert UpdateStatus.PENDING.value == "pending"
        assert UpdateStatus.IN_PROGRESS.value == "in_progress"
        assert UpdateStatus.COMPLETED.value == "completed"
        assert UpdateStatus.FAILED.value == "failed"
        assert UpdateStatus.ROLLED_BACK.value == "rolled_back"


class TestKnowledgeUpdater:
    """Test cases for KnowledgeUpdater."""

    def test_init(self) -> None:
        """Test updater initialization."""
        updater = KnowledgeUpdater(kb_id="kb_123")
        assert updater.kb_id == "kb_123"
        assert updater._vector_store is None
        assert updater._graph_store is None

    def test_init_with_stores(self) -> None:
        """Test updater initialization with stores."""
        mock_vector = MagicMock()
        mock_graph = MagicMock()
        updater = KnowledgeUpdater(
            kb_id="kb_123",
            vector_store=mock_vector,
            graph_store=mock_graph,
        )
        assert updater._vector_store is mock_vector
        assert updater._graph_store is mock_graph

    def test_create_rollback_operation(self) -> None:
        """Test rollback operation creation."""
        updater = KnowledgeUpdater(kb_id="kb_123")
        
        # Test CREATE -> DELETE
        create_op = UpdateOperation(
            target="vector_store",
            strategy=UpdateStrategy.CREATE,
            entity_id="ent_1",
            data={"text": "test"},
        )
        rollback = updater._create_rollback_operation(create_op)
        assert rollback.strategy == UpdateStrategy.DELETE
        assert rollback.entity_id == "ent_1"

    def test_create_rollback_delete(self) -> None:
        """Test rollback of DELETE creates CREATE."""
        updater = KnowledgeUpdater(kb_id="kb_123")
        
        delete_op = UpdateOperation(
            target="vector_store",
            strategy=UpdateStrategy.DELETE,
            entity_id="ent_1",
        )
        rollback = updater._create_rollback_operation(delete_op)
        assert rollback.strategy == UpdateStrategy.CREATE


class TestUpdatePlan:
    """Test cases for UpdatePlan."""

    def test_create_plan(self) -> None:
        """Test creating an update plan."""
        plan = UpdatePlan(
            kb_id="kb_123",
            operations=[
                UpdateOperation(
                    target="vector_store",
                    strategy=UpdateStrategy.CREATE,
                    entity_id="ent_1",
                    data={"text": "hello"},
                ),
            ],
        )
        assert plan.kb_id == "kb_123"
        assert len(plan.operations) == 1

    def test_plan_requires_approval(self) -> None:
        """Test plan approval requirement."""
        plan = UpdatePlan(
            kb_id="kb_123",
            operations=[
                UpdateOperation(
                    target="vector_store",
                    strategy=UpdateStrategy.DELETE,
                    entity_id="ent_1",
                ),
            ],
            requires_human_approval=True,
        )
        assert plan.requires_human_approval is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
