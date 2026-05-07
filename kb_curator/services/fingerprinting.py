"""Fingerprint computation for document change detection.

Provides:
- Content hash: Fast SHA-256 based hash
- Semantic hash: LLM-based semantic similarity hashing
- Incremental hash: For large documents
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from kb_curator.core.logging import get_logger

log = get_logger(__name__)


def compute_content_hash(content: str) -> str:
    """Compute a fast SHA-256 hash of document content.

    Args:
        content: The document content.

    Returns:
        SHA-256 hash (first 32 characters).
    """
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def compute_incremental_hash(content: str, chunk_size: int = 4096) -> str:
    """Compute an incremental hash for large documents.

    Processes content in chunks to handle large files efficiently.

    Args:
        content: The document content.
        chunk_size: Size of each chunk in bytes.

    Returns:
        Combined hash of all chunks.
    """
    hasher = hashlib.sha256()
    for i in range(0, len(content), chunk_size):
        chunk = content[i:i + chunk_size]
        hasher.update(chunk.encode())
    return hasher.hexdigest()[:32]


def normalize_content(content: str) -> str:
    """Normalize content for hashing by removing whitespace variations.

    Args:
        content: The document content.

    Returns:
        Normalized content string.
    """
    # Remove leading/trailing whitespace from each line
    normalized = "\n".join(line.strip() for line in content.splitlines())
    # Collapse multiple empty lines
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    # Remove trailing whitespace
    normalized = normalized.rstrip()
    return normalized


def compute_semantic_hash(content: str, normalize: bool = True) -> str:
    """Compute a semantic hash that ignores whitespace variations.

    Args:
        content: The document content.
        normalize: Whether to normalize content before hashing.

    Returns:
        SHA-256 hash of normalized content.
    """
    if normalize:
        content = normalize_content(content)
    return compute_content_hash(content)


def compute_diff_fingerprint(content_before: str | None, content_after: str | None) -> dict[str, Any]:
    """Compute fingerprints for change detection.

    Args:
        content_before: Content before change.
        content_after: Content after change.

    Returns:
        Dictionary with hash information.
    """
    result = {
        "hash_before": None,
        "hash_after": None,
        "content_changed": False,
        "size_delta": 0,
    }

    if content_before is not None:
        result["hash_before"] = compute_content_hash(content_before)
        result["size_before"] = len(content_before)

    if content_after is not None:
        result["hash_after"] = compute_content_hash(content_after)
        result["size_after"] = len(content_after)

    if content_before is not None and content_after is not None:
        result["content_changed"] = result["hash_before"] != result["hash_after"]
        result["size_delta"] = result["size_after"] - result["size_before"]

    return result


def compute_bow_fingerprint(content: str, top_n: int = 50) -> str:
    """Compute a bag-of-words fingerprint for rough similarity detection.

    Extracts top-N most frequent words and hashes them.

    Args:
        content: The document content.
        top_n: Number of top words to include.

    Returns:
        Hash of the bag-of-words representation.
    """
    # Tokenize (simple word extraction)
    words = re.findall(r"\b[a-zA-Z]{3,}\b", content.lower())
    if not words:
        return compute_content_hash("")

    # Count frequencies
    freq: dict[str, int] = {}
    for word in words:
        freq[word] = freq.get(word, 0) + 1

    # Get top N words by frequency
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    top_words = [w[0] for w in sorted_words[:top_n]]
    top_words.sort()  # Sort alphabetically for consistency

    # Hash the bag-of-words
    bow_str = ",".join(top_words)
    return compute_content_hash(bow_str)
