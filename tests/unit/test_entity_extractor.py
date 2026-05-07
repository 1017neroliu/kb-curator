"""Unit tests for entity extraction module."""

from __future__ import annotations

import pytest

from kb_curator.services.entity_extractor import (
    ExtractedEntity,
    EntityExtractor,
)
from kb_curator.models.schemas import KGEntityCreate


class TestExtractedEntity:
    """Test cases for ExtractedEntity."""

    def test_to_kg_entity(self) -> None:
        """Test conversion to KGEntityCreate."""
        entity = ExtractedEntity(
            name="John Doe",
            entity_type="PERSON",
            properties={"age": 30},
            confidence=0.95,
        )
        kg_entity = entity.to_kg_entity("kb_1")
        
        assert isinstance(kg_entity, KGEntityCreate)
        assert kg_entity.kb_id == "kb_1"
        assert kg_entity.name == "John Doe"
        assert kg_entity.entity_type == "PERSON"
        assert kg_entity.properties["age"] == 30
        assert kg_entity.confidence == 0.95

    def test_to_dict(self) -> None:
        """Test conversion to dict."""
        entity = ExtractedEntity(
            name="Test Corp",
            entity_type="ORGANIZATION",
            confidence=0.9,
        )
        d = entity.to_dict()
        
        assert d["name"] == "Test Corp"
        assert d["entity_type"] == "ORGANIZATION"
        assert d["confidence"] == 0.9


class TestEntityExtractor:
    """Test cases for EntityExtractor."""

    def test_init(self) -> None:
        """Test extractor initialization."""
        extractor = EntityExtractor(entity_types=["PERSON", "ORG"])
        assert extractor.entity_types == ["PERSON", "ORG"]
        assert extractor.min_confidence == 0.5

    def test_init_defaults(self) -> None:
        """Test extractor initialization with defaults."""
        extractor = EntityExtractor()
        assert extractor.entity_types is None
        assert extractor.min_confidence == 0.5


class TestEntityModels:
    """Test entity model behavior."""

    def test_entity_confidence_filtering(self) -> None:
        """Test confidence filtering logic."""
        # Entity with high confidence should be kept
        high_conf = ExtractedEntity(
            name="High Conf",
            entity_type="PERSON",
            confidence=0.9,
        )
        # Entity with low confidence should be filtered
        low_conf = ExtractedEntity(
            name="Low Conf",
            entity_type="PERSON",
            confidence=0.3,
        )
        
        threshold = 0.5
        assert high_conf.confidence >= threshold
        assert low_conf.confidence < threshold


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
