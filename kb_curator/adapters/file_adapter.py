"""File system document source adapter for local/network file directories."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from kb_curator.adapters.base import BaseDocumentSource, DocumentChange, DocumentMetadata
from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import ChangeType

log = get_logger(__name__)


class FileAdapter(BaseDocumentSource):
    """Document source adapter for monitoring local file directories.

    Supports:
    - Watching directories for file changes (create, modify, delete)
    - File pattern matching (glob patterns)
    - Content hash computation for change detection
    - Recursive directory traversal
    """

    DEFAULT_EXTENSIONS = {".txt", ".md", ".markdown", ".rst", ".json", ".yaml", ".yml", ".xml", ".html", ".htm"}

    def __init__(
        self,
        source_id: str,
        kb_id: str,
        connection_config: dict[str, Any],
    ) -> None:
        super().__init__(source_id, kb_id, connection_config)
        self.base_path = Path(connection_config.get("base_path", "."))
        self.recursive = connection_config.get("recursive", True)
        self.file_patterns = connection_config.get("file_patterns", None)  # None means all supported
        self.encoding = connection_config.get("encoding", "utf-8")

    async def list_documents(self) -> list[DocumentMetadata]:
        """List all documents in the monitored directory."""
        documents: list[DocumentMetadata] = []

        if not self.base_path.exists():
            log.warning("base_path_not_exists", base_path=str(self.base_path))
            return documents

        pattern = "**/*" if self.recursive else "*"
        files = list(self.base_path.glob(pattern))

        for file_path in files:
            if not file_path.is_file():
                continue
            if not self._is_supported_file(file_path):
                continue

            try:
                doc_id = self._get_document_id(file_path)
                content = file_path.read_text(encoding=self.encoding, errors="ignore")
                content_hash = await self.compute_content_hash(content)
                stat = file_path.stat()

                metadata = DocumentMetadata(
                    document_id=doc_id,
                    title=file_path.stem,  # filename without extension
                    content_hash=content_hash,
                    modified_at=datetime.fromtimestamp(stat.st_mtime),
                    source_url=str(file_path),
                    metadata={
                        "extension": file_path.suffix,
                        "size": stat.st_size,
                        "relative_path": str(file_path.relative_to(self.base_path)),
                    },
                )
                documents.append(metadata)

            except Exception as e:
                log.error("file_list_error", file=str(file_path), error=str(e))

        return documents

    async def poll(
        self,
        since: datetime | None = None,
        known_documents: dict[str, str] | None = None,
    ) -> list[DocumentChange]:
        """Poll for file changes since the given timestamp.

        Detects: new files, modified files, deleted files.

        Args:
            since: Only return changes after this time. None means all changes.
            known_documents: Mapping of doc_id -> content_hash for previously seen
                documents. Used to detect new/modified/deleted files without
                relying on ephemeral in-memory state.
        """
        changes: list[DocumentChange] = []
        known = known_documents or {}
        current_files = set()

        if not self.base_path.exists():
            log.warning("base_path_not_exists", base_path=str(self.base_path))
            return changes

        pattern = "**/*" if self.recursive else "*"
        files = list(self.base_path.glob(pattern))

        for file_path in files:
            if not file_path.is_file():
                continue
            if not self._is_supported_file(file_path):
                continue

            try:
                doc_id = self._get_document_id(file_path)
                current_files.add(doc_id)
                content = file_path.read_text(encoding=self.encoding, errors="ignore")
                content_hash = await self.compute_content_hash(content)
                stat = file_path.stat()
                modified_at = datetime.fromtimestamp(stat.st_mtime)

                # Check if modified since the given time
                if since and modified_at <= since:
                    continue

                previous_hash = known.get(doc_id)

                if previous_hash is None:
                    # New file
                    change = DocumentChange(
                        document_id=doc_id,
                        title=file_path.stem,
                        content_before=None,
                        content_after=content,
                        change_type=ChangeType.NEW_INFO,
                        source_url=str(file_path),
                        fingerprint_before=None,
                        fingerprint_after=content_hash,
                        metadata={
                            "extension": file_path.suffix,
                            "size": stat.st_size,
                            "relative_path": str(file_path.relative_to(self.base_path)),
                        },
                        detected_at=modified_at,
                    )
                    changes.append(change)
                    log.info("file_created", document_id=doc_id, path=str(file_path))

                elif previous_hash != content_hash:
                    # Modified file
                    change = DocumentChange(
                        document_id=doc_id,
                        title=file_path.stem,
                        content_before=None,
                        content_after=content,
                        change_type=ChangeType.POLICY_CHANGE,
                        source_url=str(file_path),
                        fingerprint_before=previous_hash,
                        fingerprint_after=content_hash,
                        metadata={
                            "extension": file_path.suffix,
                            "size": stat.st_size,
                            "relative_path": str(file_path.relative_to(self.base_path)),
                            "modified_at": modified_at.isoformat(),
                        },
                        detected_at=modified_at,
                    )
                    changes.append(change)
                    log.info("file_modified", document_id=doc_id, path=str(file_path))

            except Exception as e:
                log.error("file_poll_error", file=str(file_path), error=str(e))

        # Check for deleted files (in known_documents but not in current files)
        for doc_id in known:
            if doc_id not in current_files:
                log.info("file_deleted", document_id=doc_id)

        return changes

    async def get_content(self, document_id: str) -> str:
        """Retrieve the full content of a specific document."""
        file_path = self._get_file_path(document_id)
        if not file_path or not file_path.exists():
            raise FileNotFoundError(f"Document not found: {document_id}")
        return file_path.read_text(encoding=self.encoding, errors="ignore")

    async def health_check(self) -> bool:
        """Check if the base path is accessible."""
        try:
            if not self.base_path.exists():
                return False
            if not self.base_path.is_dir():
                return False
            # Try to list files
            list(self.base_path.glob("*"))
            return True
        except Exception as e:
            log.error("health_check_failed", path=str(self.base_path), error=str(e))
            return False

    def _is_supported_file(self, file_path: Path) -> bool:
        """Check if file extension is supported."""
        if self.file_patterns:
            # Check against glob patterns
            name = file_path.name
            for pattern in self.file_patterns:
                if re.match(pattern.replace(".", r"\.").replace("*", ".*"), name):
                    return True
            return False
        else:
            # Use default supported extensions
            return file_path.suffix.lower() in self.DEFAULT_EXTENSIONS

    def _get_document_id(self, file_path: Path) -> str:
        """Generate a document ID from file path."""
        relative = file_path.relative_to(self.base_path)
        return str(relative).replace(os.sep, "/")

    def _get_file_path(self, document_id: str) -> Path | None:
        """Get the file path from a document ID."""
        try:
            return self.base_path / document_id.replace("/", os.sep)
        except Exception:
            return None
