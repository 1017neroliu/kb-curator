"""Embedding service for knowledge extraction.

Provides:
- Text embedding generation
- Batch embedding
- Similarity computation
- Vector storage integration
"""

from __future__ import annotations

import asyncio
from typing import Any

from kb_curator.core.logging import get_logger
from kb_curator.services.llm import embedding as llm_embedding

log = get_logger(__name__)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.
    
    Args:
        a: First vector.
        b: Second vector.
        
    Returns:
        Cosine similarity score (-1 to 1).
    """
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} vs {len(b)}")
    
    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = sum(x * x for x in a) ** 0.5
    magnitude_b = sum(y * y for y in b) ** 0.5
    
    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0
    
    return dot_product / (magnitude_a * magnitude_b)


def euclidean_distance(a: list[float], b: list[float]) -> float:
    """Compute Euclidean distance between two vectors.
    
    Args:
        a: First vector.
        b: Second vector.
        
    Returns:
        Euclidean distance.
    """
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} vs {len(b)}")
    
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


class EmbeddingService:
    """Service for generating and managing embeddings."""
    
    def __init__(
        self,
        model: str | None = None,
        batch_size: int = 100,
    ) -> None:
        """Initialize the embedding service.
        
        Args:
            model: Override default embedding model.
            batch_size: Batch size for bulk embedding operations.
        """
        self.model = model
        self.batch_size = batch_size
        self._cache: dict[str, list[float]] = {}
    
    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.
        
        Args:
            text: Text to embed.
            
        Returns:
            Embedding vector.
        """
        # Check cache
        if text in self._cache:
            return self._cache[text]
        
        result = await llm_embedding(text, model=self.model)
        self._cache[text] = result
        return result
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed.
            
        Returns:
            List of embedding vectors.
        """
        # Check cache for each text
        uncached: list[tuple[int, str]] = []
        results: list[list[float] | None] = [None] * len(texts)
        
        for i, text in enumerate(texts):
            if text in self._cache:
                results[i] = self._cache[text]
            else:
                uncached.append((i, text))
        
        if uncached:
            # Batch the uncached texts
            indices = [idx for idx, _ in uncached]
            texts_to_embed = [text for _, text in uncached]
            
            for batch_start in range(0, len(texts_to_embed), self.batch_size):
                batch = texts_to_embed[batch_start:batch_start + self.batch_size]
                batch_indices = indices[batch_start:batch_start + self.batch_size]
                
                try:
                    batch_embeddings = await llm_embedding(batch, model=self.model)
                    
                    for j, emb in enumerate(batch_embeddings):
                        global_idx = batch_indices[j]
                        results[global_idx] = emb
                        text = texts_to_embed[batch_start + j]
                        self._cache[text] = emb
                        
                except Exception as e:
                    log.error("batch_embedding_failed", error=str(e))
                    # Fill with zeros on error
                    for idx in batch_indices:
                        results[idx] = [0.0] * 1024  # Placeholder dimension on error
        
        return [r for r in results if r is not None]
    
    async def compute_similarity(
        self,
        text1: str,
        text2: str,
    ) -> float:
        """Compute similarity between two texts.
        
        Args:
            text1: First text.
            text2: Second text.
            
        Returns:
            Cosine similarity score.
        """
        emb1, emb2 = await asyncio.gather(
            self.embed(text1),
            self.embed(text2),
        )
        return cosine_similarity(emb1, emb2)
    
    async def find_similar(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Find most similar candidates to a query.
        
        Args:
            query: Query text.
            candidates: List of candidate dicts with 'text' and optional 'id'.
            top_k: Number of results to return.
            score_threshold: Minimum similarity score.
            
        Returns:
            List of matched candidates with similarity scores.
        """
        if not candidates:
            return []
        
        query_emb = await self.embed(query)
        candidate_texts = [c["text"] for c in candidates]
        candidate_embs = await self.embed_batch(candidate_texts)
        
        # Compute similarities
        similarities: list[tuple[int, float]] = []
        for i, emb in enumerate(candidate_embs):
            score = cosine_similarity(query_emb, emb)
            if score >= score_threshold:
                similarities.append((i, score))
        
        # Sort by score descending
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        # Return top k
        results = []
        for idx, score in similarities[:top_k]:
            candidate = candidates[idx].copy()
            candidate["similarity_score"] = score
            if "embedding" in candidate:
                del candidate["embedding"]
            results.append(candidate)
        
        return results
    
    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        self._cache.clear()
        log.info("embedding_cache_cleared", size=len(self._cache))


# Singleton instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the singleton EmbeddingService instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
