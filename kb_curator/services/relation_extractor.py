"""Relation extraction service using LLM.

Extracts relationships between entities from text.
Supports:
- Entity pair relationship detection
- Relation type classification
- Property extraction
- Confidence scoring
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import KGRelationCreate
from kb_curator.services.llm import json_completion
from kb_curator.services.entity_extractor import ExtractedEntity

log = get_logger(__name__)


@dataclass
class ExtractedRelation:
    """A relation extracted from text."""
    source_entity: str  # Entity name or identifier
    target_entity: str  # Entity name or identifier
    relation_type: str
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source_text: str | None = None
    
    def to_kg_relation(self, kb_id: str, source_entity_id: str, target_entity_id: str) -> KGRelationCreate:
        """Convert to KGRelationCreate model."""
        return KGRelationCreate(
            kb_id=kb_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relation_type=self.relation_type,
            properties=self.properties,
            confidence=self.confidence,
        )
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "source_entity": self.source_entity,
            "target_entity": self.target_entity,
            "relation_type": self.relation_type,
            "properties": self.properties,
            "confidence": self.confidence,
            "source_text": self.source_text,
        }


RELATION_EXTRACTION_PROMPT = """You are an expert relation extraction system. Extract meaningful relationships between entities from the given text.

Common Relation Types:
- WORKS_FOR: Person works for Organization
- LOCATED_IN: Entity is located in Location
- PART_OF: Entity is part of larger entity
- CREATED_BY: Product/Artifact created by Person/Organization
- USES: Entity uses/employs another entity
- MANAGES: Person manages Person/Team/Project
- RELATED_TO: General related connection
- CAUSES: Event causes another event
- BEFORE/AFTER: Temporal ordering
- SIMILAR_TO: Similar entities
- CONTRADICTS: Contradictory information

Entities mentioned in the text:
{entities}

Text:
{text}

Respond with a JSON object containing a "relations" array:
{{
    "relations": [
        {{
            "source_entity": "entity name",
            "target_entity": "entity name",
            "relation_type": "RELATION_TYPE",
            "properties": {{
                "key": "value"
            }},
            "confidence": 0.9,
            "source_text": "sentence containing the relation"
        }}
    ]
}}

Only extract relations that are explicitly stated or strongly implied in the text. Return empty array if no relations found.
Respond ONLY with valid JSON.
"""


class RelationExtractor:
    """LLM-based relation extraction service."""
    
    def __init__(
        self,
        relation_types: list[str] | None = None,
        min_confidence: float = 0.5,
    ) -> None:
        """Initialize the relation extractor.
        
        Args:
            relation_types: List of relation types to extract (None = all).
            min_confidence: Minimum confidence threshold.
        """
        self.relation_types = relation_types
        self.min_confidence = min_confidence
    
    async def extract(
        self,
        text: str,
        entities: list[ExtractedEntity] | None = None,
    ) -> list[ExtractedRelation]:
        """Extract relations from text with known entities.
        
        Args:
            text: Input text to extract relations from.
            entities: Pre-extracted entities to find relations between.
            
        Returns:
            List of extracted relations.
        """
        if not text or len(text.strip()) < 20:
            return []
        
        try:
            # Prepare entities list for prompt
            if entities:
                entity_str = "\n".join([
                    f"- {e.name} ({e.entity_type})" 
                    for e in entities[:20]  # Limit to 20 entities
                ])
            else:
                entity_str = "Extract entities automatically from text"
            
            prompt = RELATION_EXTRACTION_PROMPT.format(
                entities=entity_str,
                text=text[:4000],
            )
            
            response = await json_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            
            data = json.loads(response)
            relations = data.get("relations", [])
            
            results: list[ExtractedRelation] = []
            for rel in relations:
                try:
                    relation = ExtractedRelation(
                        source_entity=rel.get("source_entity", "").strip(),
                        target_entity=rel.get("target_entity", "").strip(),
                        relation_type=rel.get("relation_type", "RELATED_TO").upper(),
                        properties=rel.get("properties", {}),
                        confidence=rel.get("confidence", 1.0),
                        source_text=rel.get("source_text"),
                    )
                    
                    # Filter by confidence and relation types
                    if relation.confidence >= self.min_confidence:
                        if self.relation_types is None or relation.relation_type in self.relation_types:
                            if relation.source_entity and relation.target_entity:
                                results.append(relation)
                                
                except Exception as e:
                    log.warning("relation_parse_error", relation=rel, error=str(e))
            
            log.info("relations_extracted", count=len(results), text_length=len(text))
            return results
            
        except json.JSONDecodeError as e:
            log.error("relation_extraction_json_error", error=str(e))
            return []
        except Exception as e:
            log.error("relation_extraction_failed", error=str(e))
            return []
    
    async def extract_with_entities(
        self,
        texts: list[str],
        entities_list: list[list[ExtractedEntity]],
    ) -> list[list[ExtractedRelation]]:
        """Extract relations from multiple texts with known entities.
        
        Args:
            texts: Input texts.
            entities_list: List of entity lists per text.
            
        Returns:
            List of relation lists, one per input text.
        """
        if len(texts) != len(entities_list):
            raise ValueError("texts and entities_list must have same length")
        
        results = await asyncio.gather(
            *[self.extract(text, entities) 
              for text, entities in zip(texts, entities_list)],
            return_exceptions=True,
        )
        
        # Handle exceptions
        final_results: list[list[ExtractedRelation]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.error("batch_relation_error", index=i, error=str(result))
                final_results.append([])
            else:
                final_results.append(result)
        
        return final_results


# Singleton instance
_relation_extractor: RelationExtractor | None = None


def get_relation_extractor() -> RelationExtractor:
    """Get or create the singleton RelationExtractor instance."""
    global _relation_extractor
    if _relation_extractor is None:
        _relation_extractor = RelationExtractor()
    return _relation_extractor
