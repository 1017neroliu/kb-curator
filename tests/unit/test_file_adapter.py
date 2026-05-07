"""Unit tests for FileAdapter."""

from __future__ import annotations

import asyncio
import tempfile
import os
from pathlib import Path
from datetime import datetime

import pytest

from kb_curator.adapters.file_adapter import FileAdapter
from kb_curator.adapters.base import DocumentChange
from kb_curator.models.schemas import ChangeType


class TestFileAdapter:
    """Test cases for FileAdapter."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def adapter(self, temp_dir: Path) -> FileAdapter:
        """Create a FileAdapter instance."""
        return FileAdapter(
            source_id="test-source",
            kb_id="test-kb",
            connection_config={
                "base_path": str(temp_dir),
                "recursive": True,
            },
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, adapter: FileAdapter) -> None:
        """Test health check with valid directory."""
        result = await adapter.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_invalid_path(self, temp_dir: Path) -> None:
        """Test health check with invalid directory."""
        adapter = FileAdapter(
            source_id="test-source",
            kb_id="test-kb",
            connection_config={
                "base_path": str(temp_dir / "nonexistent"),
            },
        )
        result = await adapter.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_list_documents_empty(self, adapter: FileAdapter) -> None:
        """Test listing documents from empty directory."""
        documents = await adapter.list_documents()
        assert len(documents) == 0

    @pytest.mark.asyncio
    async def test_list_documents_with_files(self, temp_dir: Path, adapter: FileAdapter) -> None:
        """Test listing documents from directory with files."""
        # Create test files
        (temp_dir / "test1.txt").write_text("Hello World", encoding="utf-8")
        (temp_dir / "test2.md").write_text("# Markdown", encoding="utf-8")
        
        # Create subdirectory
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "test3.txt").write_text("Sub file", encoding="utf-8")
        
        documents = await adapter.list_documents()
        assert len(documents) == 3
        
        # Check document metadata
        doc_ids = [d.document_id for d in documents]
        assert "test1.txt" in doc_ids
        assert "test2.md" in doc_ids
        assert "subdir/test3.txt" in doc_ids

    @pytest.mark.asyncio
    async def test_get_content(self, temp_dir: Path, adapter: FileAdapter) -> None:
        """Test retrieving content from a file."""
        content = "Test content for retrieval"
        (temp_dir / "retrieve.txt").write_text(content, encoding="utf-8")
        
        result = await adapter.get_content("retrieve.txt")
        assert result == content

    @pytest.mark.asyncio
    async def test_get_content_not_found(self, adapter: FileAdapter) -> None:
        """Test retrieving content from nonexistent file."""
        with pytest.raises(FileNotFoundError):
            await adapter.get_content("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_poll_new_file(self, temp_dir: Path, adapter: FileAdapter) -> None:
        """Test polling detects new file."""
        # First poll - should be empty
        changes = await adapter.poll()
        assert len(changes) == 0
        
        # Create a new file
        (temp_dir / "newfile.txt").write_text("New content", encoding="utf-8")
        
        # Second poll - should detect new file
        changes = await adapter.poll()
        assert len(changes) == 1
        assert changes[0].content_after == "New content"
        assert changes[0].content_before is None

    @pytest.mark.asyncio
    async def test_poll_modified_file(self, temp_dir: Path, adapter: FileAdapter) -> None:
        """Test polling detects modified file."""
        # Create initial file
        file_path = temp_dir / "modified.txt"
        file_path.write_text("Original content", encoding="utf-8")
        
        # Initial poll to cache the file
        await adapter.poll()
        
        # Modify the file
        file_path.write_text("Modified content", encoding="utf-8")
        
        # Poll again
        changes = await adapter.poll()
        assert len(changes) == 1
        assert changes[0].content_after == "Modified content"

    @pytest.mark.asyncio
    async def test_compute_fingerprint(self, temp_dir: Path, adapter: FileAdapter) -> None:
        """Test fingerprint computation."""
        (temp_dir / "file1.txt").write_text("Content 1", encoding="utf-8")
        (temp_dir / "file2.txt").write_text("Content 2", encoding="utf-8")
        
        fp1 = await adapter.compute_fingerprint()
        assert len(fp1) == 32  # SHA-256 truncated to 32 chars
        
        # Same content should produce same fingerprint
        fp2 = await adapter.compute_fingerprint()
        assert fp1 == fp2
        
        # Different content should produce different fingerprint
        (temp_dir / "file3.txt").write_text("Content 3", encoding="utf-8")
        fp3 = await adapter.compute_fingerprint()
        assert fp1 != fp3

    @pytest.mark.asyncio
    async def test_file_pattern_filter(self, temp_dir: Path) -> None:
        """Test file pattern filtering."""
        adapter = FileAdapter(
            source_id="test-source",
            kb_id="test-kb",
            connection_config={
                "base_path": str(temp_dir),
                "file_patterns": ["*.txt"],
            },
        )
        
        (temp_dir / "include.txt").write_text("Include", encoding="utf-8")
        (temp_dir / "exclude.md").write_text("Exclude", encoding="utf-8")
        
        documents = await adapter.list_documents()
        assert len(documents) == 1
        assert documents[0].document_id == "include.txt"

    @pytest.mark.asyncio
    async def test_has_changed(self, adapter: FileAdapter) -> None:
        """Test change detection."""
        # No previous fingerprint - should report changed
        assert await adapter.has_changed("abc123", None) is True
        
        # Same fingerprint - no change
        assert await adapter.has_changed("abc123", "abc123") is False
        
        # Different fingerprint - changed
        assert await adapter.has_changed("abc123", "xyz789") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
