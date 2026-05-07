"""Abstract base classes for document source adapters."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kb_curator.models.schemas import ChangeType


@dataclass
class DocumentChange:
    """Represents a detected change in a document source."""

    document_id: str
    title: str
    content_before: str | None
    content_after: str | None
    change_type: ChangeType
    source_url: str | None = None
    fingerprint_before: str | None = None
    fingerprint_after: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "document_id": self.document_id,
            "title": self.title,
            "content_before": self.content_before,
            "content_after": self.content_after,
            "change_type": self.change_type.value if isinstance(self.change_type, ChangeType) else self.change_type,
            "source_url": self.source_url,
            "fingerprint_before": self.fingerprint_before,
            "fingerprint_after": self.fingerprint_after,
            "metadata": self.metadata,
            "detected_at": self.detected_at.isoformat(),
        }


@dataclass
class DocumentMetadata:
    """Metadata for a document in a source."""

    document_id: str
    title: str
    content_hash: str
    modified_at: datetime | None = None
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseDocumentSource(ABC):
    """Abstract base class for document source adapters.

    Each adapter wraps a specific document source type (Wiki, Jira, File, etc.)
    and provides a uniform interface for polling and change detection.
    """

    def __init__(self, source_id: str, kb_id: str, connection_config: dict[str, Any]) -> None:
        self.source_id = source_id
        self.kb_id = kb_id
        self.connection_config = connection_config

    @abstractmethod
    async def poll(
        self,
        since: datetime | None = None,
        known_documents: dict[str, str] | None = None,
    ) -> list[DocumentChange]:
        """Poll the source for changes since the given timestamp.

        Args:
            since: Only return changes after this time. None means all changes.
            known_documents: Mapping of doc_id -> content_hash for previously
                seen documents. Used for deduplication without ephemeral state.

        Returns:
            List of detected document changes.
        """
        ...

    @abstractmethod
    async def list_documents(self) -> list[DocumentMetadata]:
        """List all documents in the source with their metadata.

        Returns:
            List of document metadata including IDs, titles, and content hashes.
        """
        ...

    @abstractmethod
    async def get_content(self, document_id: str) -> str:
        """Retrieve the full content of a specific document.

        Args:
            document_id: The unique identifier of the document in this source.

        Returns:
            The document content as a string.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the source is reachable and credentials are valid.

        Returns:
            True if the source is healthy, False otherwise.
        """
        ...

    async def compute_fingerprint(self) -> str:
        """Compute a fingerprint of the current source state.

        Uses content hashes of all documents for quick change detection.
        """
        documents = await self.list_documents()
        # Sort by document_id for consistent fingerprinting
        doc_hashes = sorted([doc.content_hash for doc in documents])
        fingerprint_data = json.dumps({
            "source_id": self.source_id,
            "doc_hashes": doc_hashes,
            "doc_count": len(documents),
        }, sort_keys=True)
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:32]

    async def compute_content_hash(self, content: str) -> str:
        """Compute a hash of document content.

        Args:
            content: The document content.

        Returns:
            SHA-256 hash of the content (first 32 characters).
        """
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    async def has_changed(self, current_fingerprint: str, previous_fingerprint: str | None) -> bool:
        """Check if source has changed since last poll.

        Args:
            current_fingerprint: Current computed fingerprint.
            previous_fingerprint: Fingerprint from last poll.

        Returns:
            True if fingerprints differ, False otherwise.
        """
        if previous_fingerprint is None:
            return True
        return current_fingerprint != previous_fingerprint
