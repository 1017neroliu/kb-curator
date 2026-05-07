"""Unit tests for fingerprinting module."""

from __future__ import annotations

import pytest

from kb_curator.services.fingerprinting import (
    compute_content_hash,
    compute_incremental_hash,
    normalize_content,
    compute_semantic_hash,
    compute_diff_fingerprint,
    compute_bow_fingerprint,
)


class TestFingerprinting:
    """Test cases for fingerprinting functions."""

    def test_compute_content_hash(self) -> None:
        """Test basic content hashing."""
        content = "Hello, World!"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)
        
        # Same content produces same hash
        assert hash1 == hash2
        assert len(hash1) == 32
        
        # Different content produces different hash
        hash3 = compute_content_hash("Different content")
        assert hash1 != hash3

    def test_compute_incremental_hash(self) -> None:
        """Test incremental hashing for large content."""
        content = "A" * 10000
        hash1 = compute_incremental_hash(content, chunk_size=4096)
        
        # Same content produces same hash
        hash2 = compute_incremental_hash(content, chunk_size=4096)
        assert hash1 == hash2
        
        # Different chunk size should still produce valid hash
        hash3 = compute_incremental_hash(content, chunk_size=1024)
        assert len(hash3) == 32

    def test_normalize_content(self) -> None:
        """Test content normalization."""
        # Remove extra whitespace
        content = "  Line 1  \n\n\n  Line 2  \n   "
        normalized = normalize_content(content)
        
        assert "Line 1" in normalized
        assert "Line 2" in normalized
        assert "\n\n\n" not in normalized  # Multiple newlines collapsed

    def test_compute_semantic_hash(self) -> None:
        """Test semantic hash ignores formatting differences."""
        content1 = "Hello\n\n  World"
        content2 = "Hello\n\n\n\n  World"
        
        hash1 = compute_semantic_hash(content1)
        hash2 = compute_semantic_hash(content2)
        
        # Normalized content should produce same hash
        assert hash1 == hash2

    def test_compute_diff_fingerprint(self) -> None:
        """Test diff fingerprint computation."""
        result = compute_diff_fingerprint("before", "after")
        
        assert result["hash_before"] is not None
        assert result["hash_after"] is not None
        assert result["content_changed"] is True
        
        # No change
        result2 = compute_diff_fingerprint("same", "same")
        assert result2["content_changed"] is False

    def test_compute_bow_fingerprint(self) -> None:
        """Test bag-of-words fingerprinting."""
        content1 = "apple apple apple banana"
        content2 = "banana apple apple apple"
        
        hash1 = compute_bow_fingerprint(content1)
        hash2 = compute_bow_fingerprint(content2)
        
        # Same words (different order) should produce same hash
        assert hash1 == hash2
        
        # Different words should produce different hash
        hash3 = compute_bow_fingerprint("orange grape")
        assert hash1 != hash3

    def test_empty_content(self) -> None:
        """Test handling of empty content."""
        hash1 = compute_content_hash("")
        hash2 = compute_bow_fingerprint("")
        
        assert len(hash1) == 32
        assert len(hash2) == 32


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
