"""spaCy-based pre-annotation service.

Provides NER pre-annotation to improve LLM extraction accuracy.
Supports:
- Named entity recognition
- POS tagging
- Dependency parsing
- Sentence segmentation
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from kb_curator.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class SpacyEntity:
    """Entity from spaCy NER."""
    text: str
    label: str
    start: int
    end: int
    kb_id: str | None = None  # Knowledge base entity ID if linked


@dataclass
class SpacyAnnotation:
    """Complete spaCy annotation for a text."""
    text: str
    sentences: list[str]
    entities: list[SpacyEntity]
    tokens: list[dict[str, Any]] = field(default_factory=list)
    noun_chunks: list[str] = field(default_factory=list)


# Map spaCy entity labels to our entity types
SPACY_TO_KB_TYPE = {
    "PERSON": "PERSON",
    "ORG": "ORGANIZATION",
    "GPE": "LOCATION",
    "LOC": "LOCATION",
    "FAC": "LOCATION",
    "PRODUCT": "PRODUCT",
    "EVENT": "EVENT",
    "WORK_OF_ART": "DOCUMENT",
    "LAW": "RULE",
    "LANGUAGE": "TECHNOLOGY",
    "DATE": "OTHER",
    "TIME": "OTHER",
    "MONEY": "OTHER",
    "PERCENT": "OTHER",
    "CARDINAL": "OTHER",
    "ORDINAL": "OTHER",
    "QUANTITY": "OTHER",
}


class SpacyAnnotator:
    """spaCy-based pre-annotation service."""
    
    def __init__(self, model: str = "en_core_web_sm") -> None:
        """Initialize the annotator.
        
        Args:
            model: spaCy model name.
        """
        self._nlp = None
        self._model = model
        self._enabled = True
    
    @property
    def nlp(self):
        """Lazy load spaCy model."""
        if self._nlp is None and self._enabled:
            try:
                import spacy
                self._nlp = spacy.load(self._model)
                log.info("spacy_model_loaded", model=self._model)
            except Exception as e:
                log.warning("spacy_load_failed", model=self._model, error=str(e))
                self._enabled = False
                return None
        return self._nlp
    
    def annotate(self, text: str) -> SpacyAnnotation | None:
        """Generate spaCy annotations for text.
        
        Args:
            text: Input text.
            
        Returns:
            SpacyAnnotation or None if spaCy unavailable.
        """
        if not self.nlp:
            return None
        
        try:
            doc = self.nlp(text[:50000])  # Limit to avoid memory issues
            
            # Extract sentences
            sentences = [sent.text.strip() for sent in doc.sents]
            
            # Extract entities
            entities = [
                SpacyEntity(
                    text=ent.text,
                    label=SPACY_TO_KB_TYPE.get(ent.label_, "OTHER"),
                    start=ent.start_char,
                    end=ent.end_char,
                )
                for ent in doc.ents
            ]
            
            # Extract noun chunks
            noun_chunks = [chunk.text for chunk in doc.noun_chunks]
            
            # Extract tokens (for debugging/analysis)
            tokens = [
                {
                    "text": token.text,
                    "lemma": token.lemma_,
                    "pos": token.pos_,
                    "tag": token.tag_,
                    "dep": token.dep_,
                }
                for token in doc
            ]
            
            return SpacyAnnotation(
                text=text,
                sentences=sentences,
                entities=entities,
                tokens=tokens,
                noun_chunks=noun_chunks,
            )
            
        except Exception as e:
            log.error("spacy_annotation_failed", error=str(e))
            return None
    
    def batch_annotate(self, texts: list[str]) -> list[SpacyAnnotation | None]:
        """Generate annotations for multiple texts.
        
        Args:
            texts: List of input texts.
            
        Returns:
            List of SpacyAnnotation (or None).
        """
        return [self.annotate(text) for text in texts]


# Singleton instance
_spacy_annotator: SpacyAnnotator | None = None


def get_spacy_annotator() -> SpacyAnnotator:
    """Get or create the singleton SpacyAnnotator instance."""
    global _spacy_annotator
    if _spacy_annotator is None:
        _spacy_annotator = SpacyAnnotator()
    return _spacy_annotator
