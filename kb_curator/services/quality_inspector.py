"""Quality inspection service for knowledge base maintenance.

Performs periodic quality checks:
- Expired content detection
- Low hit rate statistics
- Negative feedback tracking
- Orphan entity detection
- Metadata consistency
- Quality scoring
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import (
    QualityIssue,
    QualityIssueType,
    Severity,
)
from kb_curator.services.crud import (
    count_entries,
    list_entries,
)
from kb_curator.services.db import get_session_factory

log = get_logger(__name__)


@dataclass
class QualityReport:
    """Complete quality inspection report."""
    kb_id: str
    total_entries: int
    issues: list[QualityIssue]
    score: float  # 0.0 to 1.0
    inspection_type: str = "incremental"
    metadata: dict[str, Any] = field(default_factory=dict)


class QualityInspector:
    """Service for inspecting knowledge base quality."""

    def __init__(
        self,
        kb_id: str,
        hit_rate_threshold: float = 0.1,
        orphan_threshold_days: int = 30,
    ) -> None:
        """Initialize the inspector.

        Args:
            kb_id: Knowledge base ID.
            hit_rate_threshold: Minimum acceptable hit rate.
            orphan_threshold_days: Days before entity is considered orphan.
        """
        self.kb_id = kb_id
        self.hit_rate_threshold = hit_rate_threshold
        self.orphan_threshold_days = orphan_threshold_days
        self._graph_store = None

    @property
    def graph_store(self):
        if self._graph_store is None:
            from kb_curator.services.graph_store import get_graph_store
            self._graph_store = get_graph_store()
        return self._graph_store

    async def inspect(
        self,
        inspection_type: str = "incremental",
        entry_ids: list[str] | None = None,
    ) -> QualityReport:
        """Perform quality inspection.

        Args:
            inspection_type: Type of inspection.
                - full: All checks (expired, hit rate, orphan entities, metadata).
                - incremental: Lightweight checks only (expired, hit rate).
                - targeted: Only check specified entries (expired, metadata).
            entry_ids: Entry IDs for targeted inspection. Required if type is "targeted".

        Returns:
            QualityReport with findings and score.
        """
        issues: list[QualityIssue] = []
        metadata: dict[str, Any] = {"checks_performed": []}

        try:
            if inspection_type == "targeted":
                # Targeted: only check specified entries
                target_ids = entry_ids or []
                if not target_ids:
                    factory = get_session_factory()
                    async with factory() as session:
                        entries = await list_entries(session, self.kb_id, status="active", limit=10)
                        target_ids = [e.id for e in entries]

                expired = await self._check_expired_content(entry_ids=target_ids)
                issues.extend(expired)
                metadata["checks_performed"].append("expired")

                inconsistent = await self._check_metadata_consistency(entry_ids=target_ids)
                issues.extend(inconsistent)
                metadata["checks_performed"].append("metadata_consistency")
                metadata["targeted_entries"] = len(target_ids)

            elif inspection_type == "incremental":
                # Incremental: lightweight checks only (no graph queries)
                expired = await self._check_expired_content()
                issues.extend(expired)
                metadata["checks_performed"].append("expired")

                low_hit_rate = await self._check_low_hit_rate()
                issues.extend(low_hit_rate)
                metadata["checks_performed"].append("low_hit_rate")

            else:
                # Full: all checks
                expired = await self._check_expired_content()
                issues.extend(expired)
                metadata["expired_count"] = len(expired)
                metadata["checks_performed"].append("expired")

                low_hit_rate = await self._check_low_hit_rate()
                issues.extend(low_hit_rate)
                metadata["low_hit_rate_count"] = len(low_hit_rate)
                metadata["checks_performed"].append("low_hit_rate")

                orphans = await self._check_orphan_entities()
                issues.extend(orphans)
                metadata["orphan_count"] = len(orphans)
                metadata["checks_performed"].append("orphan_entities")

                inconsistent = await self._check_metadata_consistency()
                issues.extend(inconsistent)
                metadata["inconsistent_count"] = len(inconsistent)
                metadata["checks_performed"].append("metadata_consistency")

            # Get total entry count
            factory = get_session_factory()
            async with factory() as session:
                total = await count_entries(session, self.kb_id)
                metadata["total_entries"] = total

            # Calculate score
            score = self._calculate_score(issues, metadata.get("total_entries", 1))

            return QualityReport(
                kb_id=self.kb_id,
                total_entries=metadata.get("total_entries", 0),
                issues=issues,
                score=score,
                inspection_type=inspection_type,
                metadata=metadata,
            )

        except Exception as e:
            log.error("inspection_failed", kb_id=self.kb_id, error=str(e))
            return QualityReport(
                kb_id=self.kb_id,
                total_entries=0,
                issues=[],
                score=0.0,
                inspection_type=inspection_type,
                metadata={"error": str(e)},
            )

    async def _check_expired_content(
        self, entry_ids: list[str] | None = None
    ) -> list[QualityIssue]:
        """Check for expired knowledge entries."""
        issues: list[QualityIssue] = []
        now = datetime.utcnow()

        try:
            factory = get_session_factory()
            async with factory() as session:
                entries = await list_entries(
                    session,
                    self.kb_id,
                    status="active",
                    limit=1000,
                )

                for entry in entries:
                    # Filter by entry_ids if provided (for targeted inspection)
                    if entry_ids and entry.id not in entry_ids:
                        continue

                    if entry.expires_at and entry.expires_at < now:
                        issues.append(QualityIssue(
                            entry_id=entry.id,
                            issue_type=QualityIssueType.EXPIRED,
                            severity=Severity.WARNING,
                            detail=f"条目已于 {entry.expires_at.isoformat()} 过期",
                            suggestion="归档或更新该过期条目",
                        ))

        except Exception as e:
            log.error("expired_check_failed", error=str(e))

        return issues

    async def _check_low_hit_rate(self) -> list[QualityIssue]:
        """Check for entries with low hit rates."""
        issues: list[QualityIssue] = []

        try:
            factory = get_session_factory()
            async with factory() as session:
                entries = await list_entries(
                    session,
                    self.kb_id,
                    status="active",
                    limit=1000,
                )

                for entry in entries:
                    metadata = {}
                    try:
                        import json
                        if entry.metadata_json:
                            metadata = json.loads(entry.metadata_json)
                    except Exception:
                        pass

                    search_count = metadata.get("search_count", 0)
                    hit_count = metadata.get("hit_count", 0)

                    # Only flag low hit rate if the entry has actually been searched
                    # but never found relevant. Entries that have never been searched
                    # are not a quality issue — they just haven't been used yet.
                    if search_count > 0 and hit_count == 0:
                        issues.append(QualityIssue(
                            entry_id=entry.id,
                            issue_type=QualityIssueType.LOW_HIT_RATE,
                            severity=Severity.INFO,
                            detail=f"该条目已被搜索 {search_count} 次但从未被命中",
                            suggestion="考虑优化条目内容或添加关键词以提升检索命中率",
                        ))
                    elif search_count >= 5 and hit_count / search_count < self.hit_rate_threshold:
                        issues.append(QualityIssue(
                            entry_id=entry.id,
                            issue_type=QualityIssueType.LOW_HIT_RATE,
                            severity=Severity.INFO,
                            detail=f"该条目命中率过低（{hit_count}/{search_count}）",
                            suggestion="考虑优化条目内容或添加关键词以提升检索命中率",
                        ))

        except Exception as e:
            log.error("hit_rate_check_failed", error=str(e))

        return issues

    async def _check_orphan_entities(self) -> list[QualityIssue]:
        """Check for orphan entities in the knowledge graph."""
        issues: list[QualityIssue] = []

        try:
            # Use graph store to find orphan entities
            # An orphan is an entity with no incoming or outgoing relations
            orphan_results = await self.graph_store.find_orphan_entities(kb_id=self.kb_id)

            for result in orphan_results:
                entity_data = result.get("e", {})
                entity_id = entity_data.get("id", "")
                issues.append(QualityIssue(
                    entry_id=entity_id,
                    issue_type=QualityIssueType.ORPHAN_ENTITY,
                    severity=Severity.INFO,
                    detail="该实体没有任何关联关系，属于孤立节点",
                    suggestion="为该实体建立与其他实体的关系，或将其归档",
                ))

        except Exception as e:
            log.warning("orphan_check_failed", error=str(e))

        return issues

    async def _check_metadata_consistency(
        self, entry_ids: list[str] | None = None
    ) -> list[QualityIssue]:
        """Check for metadata consistency issues."""
        issues: list[QualityIssue] = []

        try:
            factory = get_session_factory()
            async with factory() as session:
                entries = await list_entries(
                    session,
                    self.kb_id,
                    status="active",
                    limit=1000,
                )

                for entry in entries:
                    # Filter by entry_ids if provided (for targeted inspection)
                    if entry_ids and entry.id not in entry_ids:
                        continue
                    # Check if entry has conflicting metadata
                    has_issues = False

                    # Check version consistency
                    if entry.version < 1:
                        has_issues = True

                    # Check timestamp consistency
                    if entry.created_at and entry.updated_at:
                        if entry.updated_at < entry.created_at:
                            has_issues = True

                    if has_issues:
                        issues.append(QualityIssue(
                            entry_id=entry.id,
                            issue_type=QualityIssueType.METADATA_INCONSISTENCY,
                            severity=Severity.WARNING,
                            detail="条目元数据存在不一致（版本号或时间戳异常）",
                            suggestion="检查并修复该条目的元数据",
                        ))

        except Exception as e:
            log.error("metadata_check_failed", error=str(e))

        return issues

    def _calculate_score(self, issues: list[QualityIssue], total_entries: int) -> float:
        """Calculate quality score based on issues.

        Args:
            issues: List of detected issues.
            total_entries: Total number of entries.

        Returns:
            Quality score between 0.0 and 1.0.
        """
        if total_entries == 0:
            return 1.0

        if not issues:
            return 1.0

        # Weight issues by severity
        severity_weights = {
            Severity.CRITICAL: 1.0,
            Severity.WARNING: 0.5,
            Severity.INFO: 0.05,
        }

        total_weight = 0.0
        for issue in issues:
            weight = severity_weights.get(issue.severity, 0.3)
            total_weight += weight

        # Normalize penalty by total entries; use a baseline denominator
        # so small KBs don't get disproportionately penalized
        denominator = max(total_entries, 5)
        penalty_ratio = total_weight / denominator

        # Cap penalty at 1.0 (score can't go below 0)
        score = max(0.0, 1.0 - penalty_ratio)

        return round(score, 3)


# Singleton instance factory
def create_inspector(kb_id: str, **kwargs) -> QualityInspector:
    """Create a quality inspector for a knowledge base.

    Args:
        kb_id: Knowledge base ID.
        **kwargs: Inspector configuration options.

    Returns:
        QualityInspector instance.
    """
    return QualityInspector(kb_id=kb_id, **kwargs)
