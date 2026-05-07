"""LLM-based change classifier for categorizing document changes.

Classifies changes into types:
- NEW_INFO: New knowledge added
- POLICY_CHANGE: Existing policy or rule changed
- CONTRADICTION: Content contradicts existing knowledge
- CORRECTION: Error or outdated information corrected
- REDUNDANT: Duplicate or redundant content detected
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import ChangeType
from kb_curator.services import llm as llm_module

log = get_logger(__name__)


class ChangeClassificationResult(BaseModel):
    """Result of change classification."""

    change_type: ChangeType
    confidence: float  # 0.0 to 1.0
    reasoning: str
    key_phrases: list[str] = []


CLASSIFICATION_PROMPT = """You are a document change classifier. Analyze the following document change and classify it.

Change Type Definitions:
- new_info: New knowledge, facts, or information being added to the knowledge base
- policy_change: Changes to existing policies, rules, guidelines, or procedures
- contradiction: Content that contradicts or conflicts with existing knowledge
- correction: Fixes to errors, typos, or outdated information
- redundant: Duplicate content or redundant information

Document Title: {title}

Content Before (if any):
{content_before}

Content After:
{content_after}

Respond with a JSON object:
{{
    "change_type": "one of: new_info, policy_change, contradiction, correction, redundant",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation of classification",
    "key_phrases": ["list of important phrases in the change"]
}}

Respond ONLY with valid JSON, no additional text.
"""


class ChangeClassifier:
    """LLM-based classifier for document changes."""

    async def classify(
        self,
        title: str,
        content_before: str | None,
        content_after: str,
    ) -> ChangeClassificationResult:
        """Classify a document change.

        Args:
            title: Document title.
            content_before: Content before change (None if new document).
            content_after: Content after change.

        Returns:
            Classification result with type, confidence, and reasoning.
        """
        prompt = CLASSIFICATION_PROMPT.format(
            title=title,
            content_before=content_before or "(new document)",
            content_after=content_after[:3000] if content_after else "",  # Limit context
        )

        try:
            response = await llm_module.json_completion(
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse response
            result = json.loads(response)
            change_type_str = result.get("change_type", "new_info")

            # Map string to ChangeType enum
            try:
                change_type = ChangeType(change_type_str)
            except ValueError:
                log.warning("unknown_change_type", change_type=change_type_str)
                change_type = ChangeType.NEW_INFO

            return ChangeClassificationResult(
                change_type=change_type,
                confidence=result.get("confidence", 0.5),
                reasoning=result.get("reasoning", ""),
                key_phrases=result.get("key_phrases", []),
            )

        except Exception as e:
            log.error("classification_error", error=str(e))
            # Return default classification on error
            return ChangeClassificationResult(
                change_type=ChangeType.NEW_INFO,
                confidence=0.0,
                reasoning=f"Classification failed: {str(e)}",
                key_phrases=[],
            )

    async def classify_batch(
        self,
        changes: list[dict[str, Any]],
    ) -> list[ChangeClassificationResult]:
        """Classify multiple changes in batch.

        Args:
            changes: List of change dictionaries with title, content_before, content_after.

        Returns:
            List of classification results.
        """
        results = []
        for change in changes:
            result = await self.classify(
                title=change.get("title", ""),
                content_before=change.get("content_before"),
                content_after=change.get("content_after", ""),
            )
            results.append(result)
        return results


# Singleton instance
_classifier: ChangeClassifier | None = None


def get_change_classifier() -> ChangeClassifier:
    """Get or create the singleton ChangeClassifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = ChangeClassifier()
    return _classifier
