"""FAISS vector store service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from kb_curator.core.config import get_settings
from kb_curator.core.logging import get_logger

log = get_logger(__name__)


class FAISSVectorStore:
    """FAISS-based vector store for knowledge base embeddings."""

    def __init__(self, dimension: int = 1536, index_path: Path | None = None) -> None:
        self._dimension = dimension
        self._index_path = index_path
        self._index = None  # Lazily initialized
        self._id_map: dict[int, str] = {}  # faiss_index -> chunk_id
        self._reverse_map: dict[str, int] = {}  # chunk_id -> faiss_index
        self._metadata: dict[str, dict[str, Any]] = {}  # chunk_id -> metadata

    def _ensure_index(self) -> None:
        """Lazily initialize the FAISS index."""
        if self._index is None:
            import faiss

            self._index = faiss.IndexFlatIP(self._dimension)
            # Try loading existing index
            if self._index_path:
                self._load_index()

    def _load_index(self) -> None:
        """Load an existing FAISS index and metadata from disk."""
        import faiss

        index_file = self._index_path / "faiss.index"
        meta_file = self._index_path / "metadata.npz"
        if index_file.exists() and meta_file.exists():
            self._index = faiss.read_index(str(index_file))
            data = np.load(str(meta_file), allow_pickle=True)
            self._id_map = dict(data["id_map"].item())
            self._reverse_map = dict(data["reverse_map"].item())
            self._metadata = dict(data["metadata"].item())
            log.info("faiss_index_loaded", num_vectors=self._index.ntotal)

    def save_index(self) -> None:
        """Persist the FAISS index and metadata to disk."""
        import faiss

        if self._index_path is None or self._index is None:
            return
        self._index_path.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self._index_path / "faiss.index"))
        np.savez(
            str(self._index_path / "metadata.npz"),
            id_map=self._id_map,
            reverse_map=self._reverse_map,
            metadata=self._metadata,
        )
        log.info("faiss_index_saved", num_vectors=self._index.ntotal)

    def add(self, chunk_id: str, embedding: list[float],
            metadata: dict[str, Any] | None = None) -> None:
        """Add a single vector to the index."""
        import faiss

        self._ensure_index()
        assert self._index is not None

        vec = np.array([embedding], dtype=np.float32)
        # Normalize for cosine similarity via inner product
        faiss.normalize_L2(vec)

        idx = self._index.ntotal
        self._index.add(vec)
        self._id_map[idx] = chunk_id
        self._reverse_map[chunk_id] = idx
        self._metadata[chunk_id] = metadata or {}

    def add_batch(self, chunk_ids: list[str], embeddings: list[list[float]],
                  metadatas: list[dict[str, Any] | None] | None = None) -> None:
        """Add multiple vectors to the index in a single operation.

        Args:
            chunk_ids: List of unique chunk IDs.
            embeddings: List of embedding vectors.
            metadatas: Optional list of metadata dicts for each chunk.
        """
        import faiss

        self._ensure_index()
        assert self._index is not None

        if not chunk_ids:
            return

        mat = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(mat)

        start_idx = self._index.ntotal
        self._index.add(mat)

        for i, chunk_id in enumerate(chunk_ids):
            idx = start_idx + i
            self._id_map[idx] = chunk_id
            self._reverse_map[chunk_id] = idx
            self._metadata[chunk_id] = (metadatas[i] if metadatas and i < len(metadatas) else {})

        log.debug("faiss_batch_added", count=len(chunk_ids))

    def search(self, query_embedding: list[float], top_k: int = 10,
               kb_id: str | None = None, threshold: float = 0.0) -> list[dict[str, Any]]:
        """Search for similar vectors, optionally filtered by kb_id."""
        import faiss

        self._ensure_index()
        assert self._index is not None

        if self._index.ntotal == 0:
            return []

        vec = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(vec)

        # Over-fetch to account for kb_id filtering
        fetch_k = min(top_k * 3, self._index.ntotal)
        scores, indices = self._index.search(vec, fetch_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            if score < threshold:
                continue
            chunk_id = self._id_map.get(int(idx))
            if chunk_id is None:
                continue
            meta = self._metadata.get(chunk_id, {})
            # Filter by kb_id if specified
            if kb_id and meta.get("kb_id") != kb_id:
                continue
            results.append({
                "chunk_id": chunk_id,
                "score": float(score),
                "metadata": meta,
            })
            if len(results) >= top_k:
                break

        return results

    def remove(self, chunk_ids: list[str]) -> None:
        """Remove vectors by chunk IDs.

        Note: FAISS IndexFlat does not support efficient removal.
        This rebuilds the index without the specified IDs.
        """
        import faiss

        self._ensure_index()
        assert self._index is not None

        if not chunk_ids:
            return

        # Collect IDs to keep
        keep_ids = set(self._reverse_map.keys()) - set(chunk_ids)
        if not keep_ids:
            # All removed — reset
            self._index = faiss.IndexFlatIP(self._dimension)
            self._id_map.clear()
            self._reverse_map.clear()
            self._metadata.clear()
            return

        # Rebuild index
        new_index = faiss.IndexFlatIP(self._dimension)
        new_id_map: dict[int, str] = {}
        new_reverse_map: dict[str, int] = {}

        vectors = []
        for chunk_id in keep_ids:
            old_idx = self._reverse_map[chunk_id]
            vec = self._index.reconstruct(old_idx)
            vectors.append(vec)

        if vectors:
            mat = np.vstack(vectors).astype(np.float32)
            new_index.add(mat)
            for i, chunk_id in enumerate(keep_ids):
                new_id_map[i] = chunk_id
                new_reverse_map[chunk_id] = i

        self._index = new_index
        self._id_map = new_id_map
        self._reverse_map = new_reverse_map
        # Remove metadata for deleted chunks
        for cid in chunk_ids:
            self._metadata.pop(cid, None)

    def get_chunk_ids_by_entry(self, entry_id: str) -> list[str]:
        """Get all chunk IDs belonging to a knowledge entry."""
        return [
            cid for cid, meta in self._metadata.items()
            if meta.get("entry_id") == entry_id
        ]

    @property
    def total_vectors(self) -> int:
        """Return the number of vectors in the index."""
        if self._index is None:
            return 0
        return self._index.ntotal


# ---- Singleton management per kb_id ----

_stores: dict[str, FAISSVectorStore] = {}


def get_vector_store(kb_id: str | None = None) -> FAISSVectorStore:
    """Get or create a FAISSVectorStore instance.

    If kb_id is provided, the store uses a subdirectory for that KB.
    """
    settings = get_settings()
    vs = settings.vector_store
    if kb_id:
        index_path = vs.faiss_index_path / kb_id
    else:
        index_path = vs.faiss_index_path

    key = kb_id or "__default__"
    if key not in _stores:
        store = FAISSVectorStore(
            dimension=settings.llm.embedding_dimensions,
            index_path=index_path,
        )
        _stores[key] = store
    return _stores[key]


def reset_vector_stores() -> None:
    """Reset all vector store instances — useful for testing."""
    global _stores
    _stores = {}
