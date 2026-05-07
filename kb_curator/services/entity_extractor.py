"""Entity extraction service using LLM.

Extracts entities from text chunks using LLM prompting.
Supports:
- Named entity recognition
- Entity type classification
- Property extraction
- spaCy integration for pre-annotation
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import KGEntityCreate
from kb_curator.services.llm import completion, json_completion

log = get_logger(__name__)


@dataclass
class ExtractedEntity:
    """An entity extracted from text."""
    name: str
    entity_type: str
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source_text: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    
    def to_kg_entity(self, kb_id: str, entity_id: str = "") -> KGEntityCreate:
        """Convert to KGEntityCreate model."""
        return KGEntityCreate(
            id=entity_id,
            kb_id=kb_id,
            name=self.name,
            entity_type=self.entity_type,
            properties=self.properties,
            confidence=self.confidence,
        )
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "entity_type": self.entity_type,
            "properties": self.properties,
            "confidence": self.confidence,
            "source_text": self.source_text,
            "start_char": self.start_char,
            "end_char": self.end_char,
        }


ENTITY_EXTRACTION_PROMPT = """You are an expert entity extraction system. Extract all meaningful entities from the given text.

Entity Types to recognize:
- PERSON: Human names, fictional characters
- ORGANIZATION: Companies, agencies, institutions
- PRODUCT: Products, software, services
- LOCATION: Geographic places, facilities
- EVENT: Historical events, conferences, incidents
- CONCEPT: Abstract ideas, theories, principles
- TECHNOLOGY: Technical terms, frameworks, methods
- DOCUMENT: Reports, policies, specifications
- RULE: Policies, guidelines, regulations
- OTHER: Other recognizable entities

For each entity, also extract relevant properties from the text.

Text:
{text}

Respond with a JSON object containing an "entities" array:
{{
    "entities": [
        {{
            "name": "entity name",
            "entity_type": "TYPE",
            "properties": {{
                "key": "value"
            }},
            "confidence": 0.9,
            "source_context": "surrounding text snippet"
        }}
    ]
}}

Only extract entities that are clearly identifiable from the text. Return empty array if no entities found.
Respond ONLY with valid JSON.
"""


class EntityExtractor:
    """LLM-based entity extraction service."""
    
    def __init__(
        self,
        entity_types: list[str] | None = None,
        min_confidence: float = 0.5,
    ) -> None:
        """Initialize the entity extractor.
        
        Args:
            entity_types: List of entity types to extract (None = all).
            min_confidence: Minimum confidence threshold.
        """
        self.entity_types = entity_types
        self.min_confidence = min_confidence
    
    async def extract(self, text: str) -> list[ExtractedEntity]:
        """Extract entities from a single text.
        
        Args:
            text: Input text to extract entities from.
            
        Returns:
            List of extracted entities.
        """
        if not text or len(text.strip()) < 10:
            return []
        
        try:
            prompt = ENTITY_EXTRACTION_PROMPT.format(text=text[:4000])  # Limit context
            
            response = await json_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            
            data = json.loads(response)
            entities = data.get("entities", [])
            
            results: list[ExtractedEntity] = []
            for ent in entities:
                try:
                    entity = ExtractedEntity(
                        name=ent.get("name", "").strip(),
                        entity_type=ent.get("entity_type", "OTHER").upper(),
                        properties=ent.get("properties", {}),
                        confidence=ent.get("confidence", 1.0),
                        source_text=ent.get("source_context"),
                    )
                    
                    # Filter by confidence and entity types
                    if entity.confidence >= self.min_confidence:
                        if self.entity_types is None or entity.entity_type in self.entity_types:
                            if entity.name:  # Skip empty names
                                results.append(entity)
                                
                except Exception as e:
                    log.warning("entity_parse_error", entity=ent, error=str(e))
            
            log.info("entities_extracted", count=len(results), text_length=len(text))
            return results
            
        except json.JSONDecodeError as e:
            log.error("entity_extraction_json_error", error=str(e))
            return []
        except Exception as e:
            log.error("entity_extraction_failed", error=str(e))
            return []
    
    async def extract_batch(self, texts: list[str]) -> list[list[ExtractedEntity]]:
        """Extract entities from multiple texts.
        
        Args:
            texts: List of input texts.
            
        Returns:
            List of entity lists, one per input text.
        """
        results = await asyncio.gather(
            *[self.extract(text) for text in texts],
            return_exceptions=True,
        )
        
        # Handle exceptions
        final_results: list[list[ExtractedEntity]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.error("batch_extraction_error", index=i, error=str(result))
                final_results.append([])
            else:
                final_results.append(result)
        
        return final_results


# Import asyncio for batch extraction
import asyncio


# Singleton instance
_entity_extractor: EntityExtractor | None = None


def get_entity_extractor() -> EntityExtractor:
    """Get or create the singleton EntityExtractor instance."""
    global _entity_extractor
    if _entity_extractor is None:
        _entity_extractor = EntityExtractor()
    return _entity_extractor
