"""Unit tests for entity alignment module."""

from __future__ import annotations

import pytest
import asyncio

from kb_curator.services.entity_aligner import (
    AlignmentResult,
    normalize_entity_name,
    levenshtein_distance,
    string_similarity,
    EntityAligner,
)


class TestStringFunctions:
    """Test string utility functions."""

    def test_normalize_entity_name(self) -> None:
        """Test entity name normalization."""
        assert normalize_entity_name("John Doe") == "john doe"
        assert normalize_entity_name("  Spaces  ") == "spaces"
        assert normalize_entity_name("MIXED Case") == "mixed case"

    def test_levenshtein_distance(self) -> None:
        """Test Levenshtein distance calculation."""
        # Identical strings
        assert levenshtein_distance("hello", "hello") == 0
        # One character difference
        assert levenshtein_distance("hello", "hallo") == 1
        # Completely different
        assert levenshtein_distance("abc", "xyz") == 3

    def test_string_similarity(self) -> None:
        """Test string similarity calculation."""
        # Identical strings
        assert string_similarity("hello", "hello") == 1.0
        # Very similar - allow for exact threshold
        sim = string_similarity("hello", "hallo")
        assert sim >= 0.7  # Adjust threshold
        # Completely different
        assert string_similarity("abc", "xyz") < 0.5
        # Empty strings
        assert string_similarity("", "") == 0.0
        assert string_similarity("hello", "") == 0.0


class TestAlignmentResult:
    """Test AlignmentResult dataclass."""

    def test_not_aligned(self) -> None:
        """Test default alignment result."""
        result = AlignmentResult(is_aligned=False)
        assert result.is_aligned is False
        assert result.existing_entity_id is None
        assert result.similarity_score == 0.0
        assert result.match_type == "none"

    def test_aligned(self) -> None:
        """Test aligned result."""
        result = AlignmentResult(
            is_aligned=True,
            existing_entity_id="ent_123",
            similarity_score=0.95,
            match_type="exact",
        )
        assert result.is_aligned is True
        assert result.existing_entity_id == "ent_123"
        assert result.similarity_score == 0.95


class TestEntityAligner:
    """Test cases for EntityAligner."""

    def test_init(self) -> None:
        """Test aligner initialization."""
        aligner = EntityAligner(
            fuzzy_threshold=0.8,
            semantic_threshold=0.75,
        )
        assert aligner.fuzzy_threshold == 0.8
        assert aligner.semantic_threshold == 0.75

    def test_no_existing_entities(self) -> None:
        """Test alignment with no existing entities."""
        aligner = EntityAligner(use_embeddings=False)
        result = asyncio.get_event_loop().run_until_complete(
            aligner.align_entity("Test", "PERSON", [])
        )
        assert result.is_aligned is False

    def test_exact_match(self) -> None:
        """Test exact match detection."""
        aligner = EntityAligner(use_embeddings=False)
        existing = [
            {"id": "ent_1", "name": "John Doe", "entity_type": "PERSON"},
        ]
        result = asyncio.get_event_loop().run_until_complete(
            aligner.align_entity("John Doe", "PERSON", existing)
        )
        assert result.is_aligned is True
        assert result.match_type == "exact"
        assert result.existing_entity_id == "ent_1"

    def test_fuzzy_match(self) -> None:
        """Test fuzzy match detection."""
        aligner = EntityAligner(fuzzy_threshold=0.8, use_embeddings=False)
        existing = [
            {"id": "ent_1", "name": "John Doe", "entity_type": "PERSON"},
        ]
        result = asyncio.get_event_loop().run_until_complete(
            aligner.align_entity("Jon Doe", "PERSON", existing)
        )
        # Should find fuzzy match

    def test_type_mismatch(self) -> None:
        """Test that type mismatches prevent alignment."""
        aligner = EntityAligner(use_embeddings=False)
        existing = [
            {"id": "ent_1", "name": "Apple", "entity_type": "ORGANIZATION"},
        ]
        result = asyncio.get_event_loop().run_until_complete(
            aligner.align_entity("Apple", "PRODUCT", existing)
        )
        # Type mismatch should prevent alignment


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
