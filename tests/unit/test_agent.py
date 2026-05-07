"""Unit tests for LangGraph agent module."""

from __future__ import annotations

import pytest

from kb_curator.agents.graph import (
    AgentState,
    should_interrupt,
    route_after_classify,
)


class TestAgentState:
    """Test cases for AgentState."""

    def test_empty_state(self) -> None:
        """Test creating an empty agent state."""
        state = AgentState()
        assert isinstance(state, dict)

    def test_state_with_values(self) -> None:
        """Test creating state with values."""
        state = AgentState(
            kb_id="kb_123",
            change_event_id="event_1",
            has_conflict=False,
            errors=[],
        )
        assert state["kb_id"] == "kb_123"
        assert state["change_event_id"] == "event_1"
        assert state["has_conflict"] is False


class TestRoutingFunctions:
    """Test cases for routing functions."""

    def test_should_interrupt_no_conflict(self) -> None:
        """Test routing when no conflict."""
        state = AgentState(has_conflict=False)
        result = should_interrupt(state)
        assert result == "apply_update"

    def test_should_interrupt_with_conflict(self) -> None:
        """Test routing when conflict detected."""
        state = AgentState(has_conflict=True)
        result = should_interrupt(state)
        assert result == "create_review"

    def test_route_after_classify_new_info(self) -> None:
        """Test routing after classification for new_info."""
        state = AgentState(change_type="new_info")
        result = route_after_classify(state)
        assert result == "extract_knowledge"

    def test_route_after_classify_redundant(self) -> None:
        """Test routing after classification for redundant."""
        state = AgentState(change_type="redundant")
        result = route_after_classify(state)
        assert result == "log_result"

    def test_route_after_classify_default(self) -> None:
        """Test routing after classification with no change_type."""
        state = AgentState()
        result = route_after_classify(state)
        assert result == "extract_knowledge"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
