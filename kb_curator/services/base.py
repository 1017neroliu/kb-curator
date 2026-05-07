"""Abstract base classes for vector store and graph store backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseVectorStore(ABC):
    """Abstract base class for vector store backends.

    Provides a uniform interface for adding, searching, and removing
    vector embeddings regardless of the underlying implementation
    (FAISS, Chroma, Milvus, etc.).
    """

    @abstractmethod
    async def add(self, chunk_id: str, embedding: list[float],
                  metadata: dict[str, Any] | None = None) -> None:
        """Add a single vector to the store.

        Args:
            chunk_id: Unique identifier for the text chunk.
            embedding: The embedding vector.
            metadata: Optional metadata dict (e.g., kb_id, entry_id).
        """
        ...

    @abstractmethod
    async def search(self, query_embedding: list[float], top_k: int = 10,
                     kb_id: str | None = None, threshold: float = 0.0) -> list[dict[str, Any]]:
        """Search for similar vectors.

        Args:
            query_embedding: The query embedding vector.
            top_k: Maximum number of results to return.
            kb_id: Optional knowledge base ID filter.
            threshold: Minimum similarity score threshold.

        Returns:
            List of result dicts with chunk_id, score, and metadata.
        """
        ...

    @abstractmethod
    async def remove(self, chunk_ids: list[str]) -> None:
        """Remove vectors by their chunk IDs.

        Args:
            chunk_ids: List of chunk IDs to remove.
        """
        ...

    @abstractmethod
    async def get_chunk_ids_by_entry(self, entry_id: str) -> list[str]:
        """Get all chunk IDs belonging to a knowledge entry.

        Args:
            entry_id: The knowledge entry ID.

        Returns:
            List of chunk IDs.
        """
        ...


class BaseGraphStore(ABC):
    """Abstract base class for knowledge graph store backends.

    Provides a uniform interface for entity and relation operations
    regardless of the underlying implementation (Neo4j, NetworkX, etc.).
    """

    @abstractmethod
    async def add_entity(self, kb_id: str, entity_id: str, name: str,
                         entity_type: str, properties: dict | None = None) -> None:
        """Add or merge an entity node."""
        ...

    @abstractmethod
    async def add_relation(self, kb_id: str, relation_id: str,
                           source_entity_id: str, target_entity_id: str,
                           relation_type: str, properties: dict | None = None) -> None:
        """Add a relation edge between two entities."""
        ...

    @abstractmethod
    async def get_entity(self, entity_id: str, kb_id: str) -> dict | None:
        """Get an entity by ID within a knowledge base."""
        ...

    @abstractmethod
    async def find_entity_by_name(self, name: str, entity_type: str,
                                  kb_id: str) -> dict | None:
        """Find an entity by name and type."""
        ...

    @abstractmethod
    async def find_orphan_entities(self, kb_id: str) -> list[dict]:
        """Find entities with no relations."""
        ...

    @abstractmethod
    async def delete_entity(self, entity_id: str, kb_id: str) -> None:
        """Delete an entity and its relations."""
        ...

    @abstractmethod
    async def verify_connection(self) -> bool:
        """Verify the connection to the graph store."""
        ...
