"""Text chunking strategies for knowledge extraction.

Provides:
- Fixed-size chunking with overlap
- Semantic/sentence-aware chunking
- Document-level chunking
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from kb_curator.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class Chunk:
    """A text chunk with metadata."""
    content: str
    chunk_index: int
    start_char: int
    end_char: int
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def __len__(self) -> int:
        return len(self.content)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "chunk_index": self.chunk_index,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "metadata": self.metadata,
        }


class BaseChunker(ABC):
    """Abstract base class for text chunkers."""
    
    @abstractmethod
    def chunk(self, text: str, **kwargs: Any) -> list[Chunk]:
        """Split text into chunks.
        
        Args:
            text: Input text to chunk.
            **kwargs: Chunker-specific options.
            
        Returns:
            List of Chunk objects.
        """
        ...


class FixedSizeChunker(BaseChunker):
    """Fixed-size chunker with optional overlap.
    
    Splits text into chunks of a fixed number of characters,
    with optional overlap between chunks.
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        overlap: int = 200,
        min_chunk_size: int = 100,
    ) -> None:
        """Initialize the chunker.
        
        Args:
            chunk_size: Maximum characters per chunk.
            overlap: Number of overlapping characters between chunks.
            min_chunk_size: Minimum chunk size (smaller chunks may be merged).
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size
    
    def chunk(self, text: str, **kwargs: Any) -> list[Chunk]:
        """Split text into fixed-size chunks."""
        if not text or len(text) == 0:
            return []
        
        chunks: list[Chunk] = []
        start = 0
        index = 0
        
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            
            # Try to break at sentence or paragraph boundary
            if end < len(text):
                # Look for sentence boundary
                boundary = self._find_boundary(text, start, end)
                if boundary > start:
                    end = boundary
            
            chunk_text = text[start:end]
            
            # Only add if chunk meets minimum size (or it's the last chunk)
            if len(chunk_text) >= self.min_chunk_size or end >= len(text):
                chunks.append(Chunk(
                    content=chunk_text,
                    chunk_index=index,
                    start_char=start,
                    end_char=end,
                    metadata={
                        "chunker": "fixed_size",
                        "chunk_size": self.chunk_size,
                        "overlap": self.overlap,
                    },
                ))
                index += 1
            
            # Move start with overlap
            start = end - self.overlap
            if start <= chunks[-1].end_char if chunks else start >= start:
                # Avoid infinite loop if overlap is too large
                start = end
        
        return chunks
    
    def _find_boundary(self, text: str, start: int, end: int) -> int:
        """Find a good boundary point near end."""
        # Look for sentence boundaries first: . ! ?
        sentence_pattern = r'[.!?]\s+'
        matches = list(re.finditer(sentence_pattern, text[start:end]))
        if matches:
            # Use the last sentence boundary before end
            last = matches[-1]
            boundary = start + last.end()
            # Ensure we don't go too far back
            if end - boundary < self.chunk_size // 4:
                return boundary
        
        # Look for paragraph boundaries: \n\n
        para_match = re.search(r'\n\n', text[start:end][::-1])  # reverse search
        if para_match:
            boundary = end - para_match.start()
            if end - boundary < self.chunk_size // 3:
                return boundary
        
        # Look for line break
        line_match = re.search(r'\n', text[start:end][::-1])
        if line_match:
            boundary = end - line_match.start()
            if end - boundary < self.chunk_size // 5:
                return boundary
        
        # Look for space boundary
        space_match = re.search(r' ', text[start:end][::-1])
        if space_match:
            return end - space_match.start()
        
        return end


class SemanticChunker(BaseChunker):
    """Semantic chunker that splits at natural boundaries.
    
    Attempts to split at sentence and paragraph boundaries
    while respecting a maximum chunk size.
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        min_chunk_size: int = 100,
        max_sentences: int | None = None,
    ) -> None:
        """Initialize the chunker.
        
        Args:
            chunk_size: Maximum characters per chunk.
            min_chunk_size: Minimum chunk size.
            max_sentences: Maximum sentences per chunk (optional).
        """
        self.chunk_size = chunk_size
        self.min_chunk_size = min_chunk_size
        self.max_sentences = max_sentences
    
    def chunk(self, text: str, **kwargs: Any) -> list[Chunk]:
        """Split text into semantically coherent chunks."""
        if not text or len(text) == 0:
            return []
        
        # Split into sentences
        sentences = self._split_sentences(text)
        if not sentences:
            # Fall back to character-based chunking
            return FixedSizeChunker(self.chunk_size, 0, self.min_chunk_size).chunk(text)
        
        chunks: list[Chunk] = []
        current_chunk: list[str] = []
        current_size = 0
        current_start = 0
        index = 0
        
        for sentence in sentences:
            sentence_size = len(sentence)
            
            # Check if adding this sentence would exceed chunk size
            would_exceed = current_size + sentence_size > self.chunk_size
            exceeds_max_sentences = self.max_sentences and len(current_chunk) >= self.max_sentences
            
            if (would_exceed or exceeds_max_sentences) and current_chunk:
                # Create chunk from accumulated sentences
                chunk_text = " ".join(current_chunk)
                chunks.append(Chunk(
                    content=chunk_text,
                    chunk_index=index,
                    start_char=current_start,
                    end_char=current_start + len(chunk_text),
                    metadata={
                        "chunker": "semantic",
                        "sentence_count": len(current_chunk),
                    },
                ))
                index += 1
                
                # Start new chunk with current sentence
                current_chunk = [sentence]
                current_size = sentence_size
                # Update start position
                current_start = text.find(sentence, current_start)
            else:
                current_chunk.append(sentence)
                current_size += sentence_size
        
        # Don't forget the last chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(Chunk(
                content=chunk_text,
                chunk_index=index,
                start_char=current_start,
                end_char=current_start + len(chunk_text),
                metadata={
                    "chunker": "semantic",
                    "sentence_count": len(current_chunk),
                },
            ))
        
        return chunks
    
    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Simple sentence splitting regex
        # Handles common abbreviations to avoid false splits
        pattern = r'(?<=[.!?])\s+(?=[A-Z])|(?<=\n)\s*(?=\S)'
        
        # First split by newlines for paragraph-aware splitting
        paragraphs = re.split(r'\n\s*\n', text)
        
        sentences: list[str] = []
        for para in paragraphs:
            if not para.strip():
                continue
            
            # Split each paragraph into sentences
            parts = re.split(r'(?<=[.!?])\s+', para)
            sentences.extend([s.strip() for s in parts if s.strip()])
        
        return sentences


class DocumentChunker(BaseChunker):
    """Wrapper that treats each document as a single chunk."""
    
    def chunk(self, text: str, **kwargs: Any) -> list[Chunk]:
        """Return the entire text as a single chunk."""
        if not text:
            return []
        
        return [Chunk(
            content=text,
            chunk_index=0,
            start_char=0,
            end_char=len(text),
            metadata={
                "chunker": "document",
                "is_entire_document": True,
            },
        )]


def create_chunker(
    strategy: str = "fixed",
    **kwargs: Any,
) -> BaseChunker:
    """Factory function to create chunkers.
    
    Args:
        strategy: Chunking strategy ("fixed", "semantic", "document").
        **kwargs: Strategy-specific options.
        
    Returns:
        Chunker instance.
    """
    if strategy == "fixed":
        return FixedSizeChunker(**kwargs)
    elif strategy == "semantic":
        return SemanticChunker(**kwargs)
    elif strategy == "document":
        return DocumentChunker()
    else:
        log.warning("unknown_chunker_strategy", strategy=strategy)
        return FixedSizeChunker(**kwargs)
