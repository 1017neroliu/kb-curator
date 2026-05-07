"""Conflict detection service.

Detects conflicts between new and existing knowledge:
- Semantic conflicts (LLM-based contradiction detection)
- Structural conflicts (entity property mismatches)
- Temporal conflicts (TTL and timestamp analysis)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import ConflictType, Severity
from kb_curator.services.llm import json_completion

log = get_logger(__name__)


@dataclass
class ConflictMatch:
    """A potential conflict detected between content."""
    existing_entry_id: str | None
    existing_content: str
    new_content: str
    conflict_type: ConflictType
    severity: Severity
    similarity_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class ContradictionJudgment(BaseModel):
    """LLM judgment on whether two statements contradict."""
    is_contradiction: bool
    explanation: str
    severity: Severity = Severity.WARNING
    contradiction_type: str | None = None  # e.g., "direct", "implication", "temporal"


CONTRADICTION_PROMPT = """You are an expert at detecting contradictions between statements.

Given two pieces of text, determine if they contradict each other.

Text 1 (existing knowledge):
{existing_content}

Text 2 (new information):
{new_content}

Respond with a JSON object:
{{
    "is_contradiction": true/false,
    "explanation": "brief explanation of why these do or do not contradict",
    "severity": "info/warning/critical",
    "contradiction_type": "direct/implication/temporal/none"
}}

Respond ONLY with valid JSON.
"""


class ConflictDetector:
    """Service for detecting conflicts in knowledge."""

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        semantic_threshold: float = 0.70,
        enable_llm_check: bool = True,
    ) -> None:
        """Initialize the conflict detector.

        Args:
            similarity_threshold: Threshold for vector similarity detection.
            semantic_threshold: Threshold for LLM contradiction detection.
            enable_llm_check: Whether to use LLM for deep contradiction check.
        """
        self.similarity_threshold = similarity_threshold
        self.semantic_threshold = semantic_threshold
        self.enable_llm_check = enable_llm_check
        self._embedding_service = None

    @property
    def embedding_service(self):
        if self._embedding_service is None:
            from kb_curator.services.embedding_service import get_embedding_service
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    async def detect_semantic_conflicts(
        self,
        new_content: str,
        existing_entries: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[ConflictMatch]:
        """Detect semantic conflicts using vector similarity + LLM.

        Args:
            new_content: New content to check.
            existing_entries: List of existing entries with content.
            top_k: Number of top candidates to check with LLM.

        Returns:
            List of detected conflicts.
        """
        if not existing_entries:
            return []

        conflicts: list[ConflictMatch] = []

        try:
            # Step 1: Find similar entries by embedding
            candidates = await self.embedding_service.find_similar(
                query=new_content,
                candidates=existing_entries,
                top_k=top_k,
                score_threshold=self.similarity_threshold,
            )

            # Step 2: Deep LLM check on candidates
            for candidate in candidates:
                existing_content = candidate.get("content", "")
                entry_id = candidate.get("id")

                if not existing_content:
                    continue

                if self.enable_llm_check:
                    judgment = await self._check_contradiction(
                        existing_content, new_content
                    )
                    if judgment.is_contradiction:
                        conflicts.append(ConflictMatch(
                            existing_entry_id=entry_id,
                            existing_content=existing_content,
                            new_content=new_content,
                            conflict_type=ConflictType.SEMANTIC,
                            severity=judgment.severity,
                            similarity_score=candidate.get("similarity_score", 0.0),
                            metadata={
                                "explanation": judgment.explanation,
                                "contradiction_type": judgment.contradiction_type,
                            },
                        ))
                else:
                    # Just use similarity threshold
                    if candidate.get("similarity_score", 0) >= self.similarity_threshold:
                        conflicts.append(ConflictMatch(
                            existing_entry_id=entry_id,
                            existing_content=existing_content,
                            new_content=new_content,
                            conflict_type=ConflictType.SEMANTIC,
                            severity=Severity.WARNING,
                            similarity_score=candidate.get("similarity_score", 0.0),
                        ))

        except Exception as e:
            log.error("semantic_conflict_detection_failed", error=str(e))

        return conflicts

    async def _check_contradiction(
        self,
        existing_content: str,
        new_content: str,
    ) -> ContradictionJudgment:
        """Use LLM to check for contradiction."""
        prompt = CONTRADICTION_PROMPT.format(
            existing_content=existing_content[:2000],
            new_content=new_content[:2000],
        )

        try:
            response = await json_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            data = json.loads(response)

            return ContradictionJudgment(
                is_contradiction=data.get("is_contradiction", False),
                explanation=data.get("explanation", ""),
                severity=Severity(data.get("severity", "warning")),
                contradiction_type=data.get("contradiction_type"),
            )
        except Exception as e:
            log.error("llm_contradiction_check_failed", error=str(e))
            return ContradictionJudgment(
                is_contradiction=False,
                explanation=f"LLM check failed: {str(e)}",
            )

    def detect_structural_conflicts(
        self,
        new_entity: dict[str, Any],
        existing_entity: dict[str, Any],
    ) -> list[ConflictMatch]:
        """Detect structural conflicts between entities.

        Args:
            new_entity: New entity properties.
            existing_entity: Existing entity properties.

        Returns:
            List of detected structural conflicts.
        """
        conflicts: list[ConflictMatch] = []
        new_props = new_entity.get("properties", {})
        existing_props = existing_entity.get("properties", {})

        for prop_name, new_value in new_props.items():
            existing_value = existing_props.get(prop_name)
            if existing_value is not None and existing_value != new_value:
                conflicts.append(ConflictMatch(
                    existing_entry_id=existing_entity.get("id"),
                    existing_content=f"{prop_name}: {existing_value}",
                    new_content=f"{prop_name}: {new_value}",
                    conflict_type=ConflictType.STRUCTURAL,
                    severity=Severity.WARNING,
                    metadata={
                        "property_name": prop_name,
                        "existing_value": existing_value,
                        "new_value": new_value,
                    },
                ))

        return conflicts

    def detect_temporal_conflicts(
        self,
        new_entry: dict[str, Any],
        existing_entry: dict[str, Any],
    ) -> list[ConflictMatch]:
        """Detect temporal conflicts based on timestamps and TTL.

        Args:
            new_entry: New entry with timestamp.
            existing_entry: Existing entry with timestamp.

        Returns:
            List of detected temporal conflicts.
        """
        conflicts: list[ConflictMatch] = []

        # Check if existing entry has expired
        expires_at = existing_entry.get("expires_at")
        if expires_at:
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            if expires_at < datetime.utcnow():
                # Existing entry is expired, no conflict
                return conflicts

        # Check for timestamp ordering
        new_updated = new_entry.get("updated_at") or new_entry.get("created_at")
        existing_updated = existing_entry.get("updated_at") or existing_entry.get("created_at")

        if new_updated and existing_updated:
            if isinstance(new_updated, str):
                new_updated = datetime.fromisoformat(new_updated)
            if isinstance(existing_updated, str):
                existing_updated = datetime.fromisoformat(existing_updated)

            # New entry is older than existing - potential conflict
            if new_updated < existing_updated:
                conflicts.append(ConflictMatch(
                    existing_entry_id=existing_entry.get("id"),
                    existing_content=f"Updated: {existing_updated}",
                    new_content=f"Updated: {new_updated}",
                    conflict_type=ConflictType.TEMPORAL,
                    severity=Severity.INFO,
                    metadata={
                        "existing_timestamp": str(existing_updated),
                        "new_timestamp": str(new_updated),
                    },
                ))

        return conflicts

    async def detect_all_conflicts(
        self,
        new_content: str,
        existing_entries: list[dict[str, Any]],
        new_entity: dict[str, Any] | None = None,
        existing_entity: dict[str, Any] | None = None,
    ) -> list[ConflictMatch]:
        """Detect all types of conflicts.

        Args:
            new_content: New content to check.
            existing_entries: List of existing entries.
            new_entity: Optional new entity for structural check.
            existing_entity: Optional existing entity for structural check.

        Returns:
            List of all detected conflicts.
        """
        all_conflicts: list[ConflictMatch] = []

        # Semantic conflicts
        semantic = await self.detect_semantic_conflicts(new_content, existing_entries)
        all_conflicts.extend(semantic)

        # Structural conflicts
        if new_entity and existing_entity:
            structural = self.detect_structural_conflicts(new_entity, existing_entity)
            all_conflicts.extend(structural)

        # Temporal conflicts
        if existing_entries:
            for entry in existing_entries[:1]:  # Check most recent
                temporal = self.detect_temporal_conflicts(
                    {"updated_at": datetime.utcnow()},  # Simulate new entry
                    entry,
                )
                all_conflicts.extend(temporal)

        return all_conflicts


# Singleton instance
_conflict_detector: ConflictDetector | None = None


def get_conflict_detector() -> ConflictDetector:
    """Get or create the singleton ConflictDetector instance."""
    global _conflict_detector
    if _conflict_detector is None:
        _conflict_detector = ConflictDetector()
    return _conflict_detector
