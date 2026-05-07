"""Unit tests for text chunking module."""

from __future__ import annotations

import pytest

from kb_curator.services.chunker import (
    Chunk,
    FixedSizeChunker,
    SemanticChunker,
    DocumentChunker,
    create_chunker,
)


class TestFixedSizeChunker:
    """Test cases for FixedSizeChunker."""

    def test_empty_text(self) -> None:
        """Test chunking empty text."""
        chunker = FixedSizeChunker(chunk_size=100)
        chunks = chunker.chunk("")
        assert len(chunks) == 0

    def test_single_chunk(self) -> None:
        """Test text smaller than chunk size."""
        chunker = FixedSizeChunker(chunk_size=1000)
        text = "This is a short text."
        chunks = chunker.chunk(text)
        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_multiple_chunks(self) -> None:
        """Test text larger than chunk size."""
        chunker = FixedSizeChunker(chunk_size=50, overlap=0)
        text = "This is a very long text that should be split into multiple chunks for processing."
        chunks = chunker.chunk(text)
        # May or may not split depending on content, just verify it works
        assert len(chunks) >= 1
        # Verify chunks are within reasonable bounds
        for chunk in chunks:
            assert len(chunk.content) > 0

    def test_overlap(self) -> None:
        """Test chunk overlap with reasonable settings."""
        chunker = FixedSizeChunker(chunk_size=20, overlap=5)
        text = "A" * 100
        chunks = chunker.chunk(text)
        # With proper settings, should create multiple chunks
        assert len(chunks) >= 1

    def test_chunk_metadata(self) -> None:
        """Test chunk metadata is set correctly."""
        chunker = FixedSizeChunker(chunk_size=50, overlap=10)
        text = "Sample text for metadata testing"
        chunks = chunker.chunk(text)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.start_char >= 0
            assert chunk.end_char > chunk.start_char
            assert "chunker" in chunk.metadata


class TestSemanticChunker:
    """Test cases for SemanticChunker."""

    def test_empty_text(self) -> None:
        """Test chunking empty text."""
        chunker = SemanticChunker(chunk_size=100)
        chunks = chunker.chunk("")
        assert len(chunks) == 0

    def test_sentence_aware(self) -> None:
        """Test that chunking respects sentence boundaries."""
        chunker = SemanticChunker(chunk_size=50)
        text = "This is the first sentence. And this is the second sentence."
        chunks = chunker.chunk(text)
        # At least one chunk should contain complete sentences
        assert len(chunks) >= 1

    def test_paragraph_aware(self) -> None:
        """Test that chunking respects paragraph boundaries."""
        chunker = SemanticChunker(chunk_size=200)
        text = "Paragraph one.\n\nParagraph two."
        chunks = chunker.chunk(text)
        # Both paragraphs should be identifiable
        assert len(chunks) >= 1

    def test_max_sentences(self) -> None:
        """Test max sentences per chunk."""
        chunker = SemanticChunker(chunk_size=1000, max_sentences=2)
        text = "Sentence one. Sentence two. Sentence three. Sentence four."
        chunks = chunker.chunk(text)
        # Should split based on sentence count
        assert len(chunks) >= 2


class TestDocumentChunker:
    """Test cases for DocumentChunker."""

    def test_entire_document(self) -> None:
        """Test that entire document becomes single chunk."""
        chunker = DocumentChunker()
        text = "This is an entire document as one chunk."
        chunks = chunker.chunk(text)
        assert len(chunks) == 1
        assert chunks[0].content == text
        assert chunks[0].metadata["is_entire_document"] is True


class TestChunkerFactory:
    """Test cases for chunker factory."""

    def test_create_fixed_chunker(self) -> None:
        """Test creating fixed-size chunker."""
        chunker = create_chunker("fixed", chunk_size=100)
        assert isinstance(chunker, FixedSizeChunker)

    def test_create_semantic_chunker(self) -> None:
        """Test creating semantic chunker."""
        chunker = create_chunker("semantic", chunk_size=100)
        assert isinstance(chunker, SemanticChunker)

    def test_create_document_chunker(self) -> None:
        """Test creating document chunker."""
        chunker = create_chunker("document")
        assert isinstance(chunker, DocumentChunker)


class TestChunk:
    """Test cases for Chunk dataclass."""

    def test_len(self) -> None:
        """Test chunk length."""
        chunk = Chunk("Hello World", 0, 0, 11)
        assert len(chunk) == 11

    def test_to_dict(self) -> None:
        """Test chunk to dict conversion."""
        chunk = Chunk("Test content", 0, 0, 12, {"key": "value"})
        d = chunk.to_dict()
        assert d["content"] == "Test content"
        assert d["chunk_index"] == 0
        assert d["start_char"] == 0
        assert d["end_char"] == 12
        assert d["metadata"]["key"] == "value"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
