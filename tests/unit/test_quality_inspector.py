"""Unit tests for quality inspection module."""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta

from kb_curator.models.schemas import QualityIssueType, Severity
from kb_curator.services.quality_inspector import (
    QualityInspector,
    QualityReport,
)


class TestQualityReport:
    """Test cases for QualityReport."""

    def test_create_report(self) -> None:
        """Test creating a quality report."""
        report = QualityReport(
            kb_id="kb_123",
            total_entries=100,
            issues=[],
            score=0.95,
            inspection_type="incremental",
        )
        assert report.kb_id == "kb_123"
        assert report.total_entries == 100
        assert report.score == 0.95
        assert report.inspection_type == "incremental"


class TestQualityInspector:
    """Test cases for QualityInspector."""

    def test_init(self) -> None:
        """Test inspector initialization."""
        inspector = QualityInspector(kb_id="kb_123")
        assert inspector.kb_id == "kb_123"
        assert inspector.hit_rate_threshold == 0.1
        assert inspector.orphan_threshold_days == 30

    def test_init_custom(self) -> None:
        """Test inspector with custom settings."""
        inspector = QualityInspector(
            kb_id="kb_123",
            hit_rate_threshold=0.2,
            orphan_threshold_days=60,
        )
        assert inspector.hit_rate_threshold == 0.2
        assert inspector.orphan_threshold_days == 60


class TestQualityScoreCalculation:
    """Test cases for quality score calculation."""

    def test_calculate_score_no_issues(self) -> None:
        """Test score with no issues."""
        inspector = QualityInspector(kb_id="kb_123")
        score = inspector._calculate_score([], 100)
        assert score == 1.0

    def test_calculate_score_with_issues(self) -> None:
        """Test score calculation with issues."""
        inspector = QualityInspector(kb_id="kb_123")
        
        from kb_curator.models.schemas import QualityIssue
        issues = [
            QualityIssue(
                entry_id="e1",
                issue_type=QualityIssueType.EXPIRED,
                severity=Severity.WARNING,
                detail="Test",
                suggestion="Test",
            ),
        ]
        score = inspector._calculate_score(issues, 100)
        assert 0.0 <= score <= 1.0

    def test_calculate_score_zero_entries(self) -> None:
        """Test score with zero entries."""
        inspector = QualityInspector(kb_id="kb_123")
        score = inspector._calculate_score([], 0)
        assert score == 1.0

    def test_calculate_score_critical_severity(self) -> None:
        """Test that critical severity issues reduce score more."""
        inspector = QualityInspector(kb_id="kb_123")
        
        from kb_curator.models.schemas import QualityIssue
        issues = [
            QualityIssue(
                entry_id="e1",
                issue_type=QualityIssueType.EXPIRED,
                severity=Severity.CRITICAL,
                detail="Critical issue",
                suggestion="Fix immediately",
            ),
        ]
        critical_score = inspector._calculate_score(issues, 100)
        
        info_issues = [
            QualityIssue(
                entry_id="e1",
                issue_type=QualityIssueType.EXPIRED,
                severity=Severity.INFO,
                detail="Info issue",
                suggestion="Consider fixing",
            ),
        ]
        info_score = inspector._calculate_score(info_issues, 100)
        
        # Critical should reduce score more
        assert critical_score < info_score


class TestQualityIssueTypes:
    """Test quality issue type enumeration."""

    def test_issue_types(self) -> None:
        """Test all issue types are defined."""
        assert QualityIssueType.LOW_HIT_RATE.value == "low_hit_rate"
        assert QualityIssueType.HIGH_NEGATIVE_FEEDBACK.value == "high_negative_feedback"
        assert QualityIssueType.EXPIRED.value == "expired"
        assert QualityIssueType.ORPHAN_ENTITY.value == "orphan_entity"
        assert QualityIssueType.METADATA_INCONSISTENCY.value == "metadata_inconsistency"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
