"""Unit tests for conflict detection module."""

from __future__ import annotations

import pytest

from kb_curator.models.schemas import ConflictType, Severity
from kb_curator.services.conflict_detector import (
    ConflictMatch,
    ContradictionJudgment,
    ConflictDetector,
)


class TestConflictMatch:
    """Test cases for ConflictMatch."""

    def test_create_conflict_match(self) -> None:
        """Test creating a conflict match."""
        match = ConflictMatch(
            existing_entry_id="entry_123",
            existing_content="The sky is blue",
            new_content="The sky is green",
            conflict_type=ConflictType.SEMANTIC,
            severity=Severity.WARNING,
            similarity_score=0.95,
        )
        
        assert match.existing_entry_id == "entry_123"
        assert match.conflict_type == ConflictType.SEMANTIC
        assert match.severity == Severity.WARNING
        assert match.similarity_score == 0.95

    def test_conflict_match_default_severity(self) -> None:
        """Test default severity is WARNING."""
        match = ConflictMatch(
            existing_entry_id=None,
            existing_content="Old content",
            new_content="New content",
            conflict_type=ConflictType.STRUCTURAL,
            severity=Severity.WARNING,
        )
        assert match.severity == Severity.WARNING


class TestContradictionJudgment:
    """Test cases for ContradictionJudgment."""

    def test_create_contradiction(self) -> None:
        """Test creating a contradiction judgment."""
        judgment = ContradictionJudgment(
            is_contradiction=True,
            explanation="The statements contradict each other",
            severity=Severity.CRITICAL,
            contradiction_type="direct",
        )
        
        assert judgment.is_contradiction is True
        assert judgment.severity == Severity.CRITICAL
        assert judgment.contradiction_type == "direct"

    def test_no_contradiction(self) -> None:
        """Test non-contradiction judgment."""
        judgment = ContradictionJudgment(
            is_contradiction=False,
            explanation="Statements are compatible",
        )
        assert judgment.is_contradiction is False
        assert judgment.contradiction_type is None


class TestConflictDetector:
    """Test cases for ConflictDetector."""

    def test_init(self) -> None:
        """Test detector initialization."""
        detector = ConflictDetector(
            similarity_threshold=0.9,
            semantic_threshold=0.8,
        )
        assert detector.similarity_threshold == 0.9
        assert detector.semantic_threshold == 0.8
        assert detector.enable_llm_check is True

    def test_init_defaults(self) -> None:
        """Test detector initialization with defaults."""
        detector = ConflictDetector()
        assert detector.similarity_threshold == 0.85
        assert detector.semantic_threshold == 0.70

    def test_detect_structural_conflicts_no_conflict(self) -> None:
        """Test structural conflict detection with matching properties."""
        detector = ConflictDetector()
        new_entity = {
            "id": "new_1",
            "name": "Test Entity",
            "properties": {"color": "blue", "size": "large"},
        }
        existing_entity = {
            "id": "existing_1",
            "name": "Test Entity",
            "properties": {"color": "blue", "size": "large"},
        }
        
        conflicts = detector.detect_structural_conflicts(new_entity, existing_entity)
        assert len(conflicts) == 0

    def test_detect_structural_conflicts_with_conflict(self) -> None:
        """Test structural conflict detection with mismatched properties."""
        detector = ConflictDetector()
        new_entity = {
            "id": "new_1",
            "name": "Test Entity",
            "properties": {"color": "red", "size": "large"},
        }
        existing_entity = {
            "id": "existing_1",
            "name": "Test Entity",
            "properties": {"color": "blue", "size": "large"},
        }
        
        conflicts = detector.detect_structural_conflicts(new_entity, existing_entity)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.STRUCTURAL
        assert conflicts[0].metadata["property_name"] == "color"
        assert conflicts[0].metadata["existing_value"] == "blue"
        assert conflicts[0].metadata["new_value"] == "red"


class TestConflictTypes:
    """Test conflict type enumeration."""

    def test_conflict_types(self) -> None:
        """Test all conflict types are defined."""
        assert ConflictType.SEMANTIC.value == "semantic"
        assert ConflictType.STRUCTURAL.value == "structural"
        assert ConflictType.TEMPORAL.value == "temporal"


class TestSeverityLevels:
    """Test severity level enumeration."""

    def test_severity_levels(self) -> None:
        """Test all severity levels are defined."""
        assert Severity.INFO.value == "info"
        assert Severity.WARNING.value == "warning"
        assert Severity.CRITICAL.value == "critical"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
