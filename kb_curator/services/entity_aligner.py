"""Entity alignment service.

Aligns extracted entities with existing knowledge graph entities.
Supports:
- Fuzzy string matching
- Embedding-based similarity
- Type compatibility checking
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kb_curator.core.logging import get_logger
from kb_curator.services.embedding_service import get_embedding_service, cosine_similarity

log = get_logger(__name__)


@dataclass
class AlignmentResult:
    """Result of entity alignment."""
    is_aligned: bool
    existing_entity_id: str | None = None
    similarity_score: float = 0.0
    match_type: str = "none"  # none, exact, fuzzy, semantic
    merged_properties: dict[str, Any] | None = None


def normalize_entity_name(name: str) -> str:
    """Normalize entity name for comparison."""
    return name.lower().strip()


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def string_similarity(s1: str, s2: str) -> float:
    """Calculate string similarity using Levenshtein distance."""
    if not s1 or not s2:
        return 0.0
    
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    
    distance = levenshtein_distance(s1.lower(), s2.lower())
    return 1.0 - (distance / max_len)


class EntityAligner:
    """Entity alignment service."""
    
    def __init__(
        self,
        fuzzy_threshold: float = 0.85,
        semantic_threshold: float = 0.80,
        use_embeddings: bool = True,
    ) -> None:
        """Initialize the aligner.
        
        Args:
            fuzzy_threshold: Minimum fuzzy string similarity.
            semantic_threshold: Minimum embedding similarity.
            use_embeddings: Whether to use embedding-based matching.
        """
        self.fuzzy_threshold = fuzzy_threshold
        self.semantic_threshold = semantic_threshold
        self.use_embeddings = use_embeddings
        self._embedding_service = None
    
    @property
    def embedding_service(self):
        if self._embedding_service is None and self.use_embeddings:
            self._embedding_service = get_embedding_service()
        return self._embedding_service
    
    async def align_entity(
        self,
        entity_name: str,
        entity_type: str,
        existing_entities: list[dict[str, Any]],
    ) -> AlignmentResult:
        """Align a new entity with existing entities.
        
        Args:
            entity_name: Name of the entity to align.
            entity_type: Type of the entity.
            existing_entities: List of existing entities with id, name, type.
            
        Returns:
            AlignmentResult indicating if alignment was found.
        """
        if not existing_entities:
            return AlignmentResult(is_aligned=False)
        
        normalized_name = normalize_entity_name(entity_name)
        
        best_match: AlignmentResult = AlignmentResult(is_aligned=False)
        
        for existing in existing_entities:
            existing_name = normalize_entity_name(existing.get("name", ""))
            existing_type = existing.get("entity_type", "")
            
            # Type check - must match
            if existing_type and existing_type != entity_type:
                continue
            
            # Exact match
            if normalized_name == existing_name:
                return AlignmentResult(
                    is_aligned=True,
                    existing_entity_id=existing.get("id"),
                    similarity_score=1.0,
                    match_type="exact",
                )
            
            # Fuzzy string matching
            str_sim = string_similarity(entity_name, existing.get("name", ""))
            if str_sim >= self.fuzzy_threshold and str_sim > best_match.similarity_score:
                best_match = AlignmentResult(
                    is_aligned=True,
                    existing_entity_id=existing.get("id"),
                    similarity_score=str_sim,
                    match_type="fuzzy",
                )
        
        # Semantic similarity (embedding-based)
        if self.embedding_service and best_match.similarity_score < 1.0:
            try:
                embeddings = await self.embedding_service.embed_batch([
                    entity_name,
                    *[e.get("name", "") for e in existing_entities],
                ])
                
                entity_emb = embeddings[0]
                for i, existing in enumerate(existing_entities):
                    existing_emb = embeddings[i + 1]
                    if existing_emb is None:
                        continue
                    
                    sem_sim = cosine_similarity(entity_emb, existing_emb)
                    if sem_sim >= self.semantic_threshold and sem_sim > best_match.similarity_score:
                        # Check type compatibility
                        if existing.get("entity_type") in (entity_type, ""):
                            best_match = AlignmentResult(
                                is_aligned=True,
                                existing_entity_id=existing.get("id"),
                                similarity_score=sem_sim,
                                match_type="semantic",
                            )
                            
            except Exception as e:
                log.warning("embedding_alignment_error", error=str(e))
        
        return best_match
    
    async def align_entities_batch(
        self,
        new_entities: list[dict[str, Any]],
        existing_entities: list[dict[str, Any]],
    ) -> list[AlignmentResult]:
        """Align multiple entities in batch.
        
        Args:
            new_entities: List of new entities to align.
            existing_entities: List of existing entities.
            
        Returns:
            List of AlignmentResults.
        """
        import asyncio
        results = await asyncio.gather(
            *[self.align_entity(
                e.get("name", ""),
                e.get("entity_type", ""),
                existing_entities,
            ) for e in new_entities],
            return_exceptions=True,
        )
        
        final_results: list[AlignmentResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                log.error("batch_align_error", index=i, error=str(result))
                final_results.append(AlignmentResult(is_aligned=False))
            else:
                final_results.append(result)
        
        return final_results


# Singleton instance
_entity_aligner: EntityAligner | None = None


def get_entity_aligner() -> EntityAligner:
    """Get or create the singleton EntityAligner instance."""
    global _entity_aligner
    if _entity_aligner is None:
        _entity_aligner = EntityAligner()
    return _entity_aligner
