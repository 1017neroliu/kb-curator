"""Document source polling service with APScheduler integration."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kb_curator.adapters.confluence_adapter import ConfluenceAdapter
from kb_curator.adapters.file_adapter import FileAdapter
from kb_curator.adapters.jira_adapter import JiraAdapter
from kb_curator.adapters.webpage_adapter import WebpageAdapter
from kb_curator.adapters.wiki_adapter import WikiAdapter
from kb_curator.adapters.base import BaseDocumentSource, DocumentChange
from kb_curator.core.config import get_settings
from kb_curator.core.logging import get_logger
from kb_curator.models.db_tables import KnowledgeEntryTable
from kb_curator.models.schemas import ChangeType
from kb_curator.services.crud import (
    create_change_event,
    create_entry,
    list_data_sources,
    update_data_source,
)
from kb_curator.services.db import get_session
from kb_curator.services.change_classifier import get_change_classifier

log = get_logger(__name__)


def create_adapter(
    source_type: str,
    source_id: str,
    kb_id: str,
    connection_config: dict[str, Any],
) -> BaseDocumentSource:
    """Factory function to create document source adapters.

    Args:
        source_type: Type of source (file, wiki, confluence, etc.)
        source_id: Unique ID of the source.
        kb_id: Knowledge base ID.
        connection_config: Source-specific configuration.

    Returns:
        Appropriate adapter instance.
    """
    if source_type == "file":
        return FileAdapter(source_id, kb_id, connection_config)
    elif source_type == "wiki":
        return WikiAdapter(source_id, kb_id, connection_config)
    elif source_type == "confluence":
        return ConfluenceAdapter(source_id, kb_id, connection_config)
    elif source_type == "jira":
        return JiraAdapter(source_id, kb_id, connection_config)
    elif source_type == "webpage":
        return WebpageAdapter(source_id, kb_id, connection_config)
    else:
        raise ValueError(f"Unsupported source type: {source_type}")


async def _build_known_documents(
    session: AsyncSession,
    kb_id: str,
    source_id: str,
) -> dict[str, str]:
    """Build a mapping of document_id -> content_hash from existing entries.

    This is used to deduplicate: if a file was already ingested with the same
    content hash, we skip it on the next poll.
    """
    stmt = (
        select(KnowledgeEntryTable)
        .where(KnowledgeEntryTable.kb_id == kb_id)
        .where(KnowledgeEntryTable.source_id == source_id)
    )
    result = await session.execute(stmt)
    entries = result.scalars().all()

    known: dict[str, str] = {}
    for entry in entries:
        meta_raw = entry.metadata_json
        try:
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
        except (json.JSONDecodeError, TypeError):
            meta = {}
        # Use fingerprint_after (content hash) stored at ingestion time
        fingerprint = meta.get("fingerprint_after")
        # Prefer document_id stored in metadata (matches FileAdapter doc IDs)
        doc_id = meta.get("document_id") or entry.title
        if fingerprint and doc_id:
            known[doc_id] = fingerprint
    return known


async def poll_data_source(
    session: AsyncSession,
    source: Any,
    classifier: Any | None = None,
    create_entries: bool = False,
) -> list[DocumentChange]:
    """Poll a single data source for changes.

    Args:
        session: Database session.
        source: DataSourceTable instance.
        classifier: Optional change classifier.
        create_entries: If True, create knowledge entries from detected changes
            and run the extraction pipeline.

    Returns:
        List of detected changes.
    """
    try:
        # Parse connection config
        config = json.loads(source.connection_config) if isinstance(source.connection_config, str) else source.connection_config

        # Create adapter
        adapter = create_adapter(
            source_type=source.source_type,
            source_id=source.id,
            kb_id=source.kb_id,
            connection_config=config,
        )

        # Check health first
        if not await adapter.health_check():
            log.warning("source_unhealthy", source_id=source.id)
            return []

        # Build known documents for deduplication
        known_documents = await _build_known_documents(session, source.kb_id, source.id)

        # Poll for changes
        changes = await adapter.poll(
            since=source.last_polled_at,
            known_documents=known_documents,
        )

        if not changes:
            log.info("no_changes_detected", source_id=source.id)
            # Still update polling timestamp
            fingerprint = await adapter.compute_fingerprint()
            await update_data_source(
                session,
                source.id,
                last_polled_at=datetime.utcnow(),
                last_fingerprint=fingerprint,
            )
            return []

        # Classify changes using LLM if classifier provided
        if classifier:
            for change in changes:
                try:
                    result = await classifier.classify(
                        title=change.title,
                        content_before=change.content_before,
                        content_after=change.content_after or "",
                    )
                    change.change_type = result.change_type
                except Exception as e:
                    log.error("classification_failed", error=str(e))

        # Save changes to database
        for change in changes:
            await create_change_event(
                session,
                kb_id=source.kb_id,
                source_id=source.id,
                change_type=change.change_type.value if isinstance(change.change_type, ChangeType) else change.change_type,
                title=change.title,
                content_before=change.content_before,
                content_after=change.content_after,
                fingerprint_before=change.fingerprint_before,
                fingerprint_after=change.fingerprint_after,
                metadata=change.metadata,
            )

        # Create entries and run extraction if requested
        if create_entries:
            from kb_curator.services.knowledge_extractor import create_extractor

            for change in changes:
                content = change.content_after or change.content_before
                if not content:
                    continue

                entry = await create_entry(
                    session,
                    kb_id=source.kb_id,
                    title=change.title,
                    content=content,
                    source_id=source.id,
                    source_url=change.source_url,
                    tags=["polled"],
                    metadata={
                        "change_type": change.change_type.value if hasattr(change.change_type, 'value') else str(change.change_type),
                        "fingerprint_after": change.fingerprint_after,
                        "document_id": change.document_id,
                        "processed": True,
                        "extraction_summary": {},
                    },
                )

                # Run extraction pipeline
                try:
                    extractor = create_extractor(kb_id=source.kb_id, source_id=source.id)
                    extraction = await extractor.extract_and_store(
                        text=content,
                        entry_id=entry.id,
                    )
                    # Update entry with extraction results
                    from kb_curator.services.crud import update_entry
                    await update_entry(
                        session,
                        entry.id,
                        metadata={
                            "change_type": change.change_type.value if hasattr(change.change_type, 'value') else str(change.change_type),
                            "fingerprint_after": change.fingerprint_after,
                            "document_id": change.document_id,
                            "processed": True,
                            "extraction_summary": {
                                "entities": len(extraction.entities),
                                "relations": len(extraction.relations),
                                "chunks": len(extraction.text_chunks),
                            },
                        },
                    )
                except Exception as e:
                    log.error("extraction_failed", entry_id=entry.id, error=str(e))

        # Update source polling timestamp and fingerprint
        fingerprint = await adapter.compute_fingerprint()
        await update_data_source(
            session,
            source.id,
            last_polled_at=datetime.utcnow(),
            last_fingerprint=fingerprint,
        )

        log.info(
            "changes_detected",
            source_id=source.id,
            change_count=len(changes),
        )

        return changes

    except Exception as e:
        log.error("poll_data_source_failed", source_id=source.id, error=str(e))
        return []


async def poll_all_sources() -> dict[str, Any]:
    """Poll all enabled data sources across all knowledge bases.

    This function is registered as an APScheduler job.
    Unlike poll_data_source, this also creates entries automatically.

    Returns:
        Summary of polling results.
    """
    results: dict[str, Any] = {
        "total_sources": 0,
        "polled_sources": 0,
        "total_changes": 0,
        "entries_created": 0,
        "errors": [],
    }

    try:
        async for session in get_session():
            # Get all enabled data sources
            sources = await list_data_sources(session, enabled_only=True)
            results["total_sources"] = len(sources)

            classifier = get_change_classifier()

            for source in sources:
                try:
                    changes = await poll_data_source(
                        session, source, classifier, create_entries=True,
                    )
                    results["polled_sources"] += 1
                    results["total_changes"] += len(changes)
                    results["entries_created"] += len([
                        c for c in changes if (c.content_after or c.content_before)
                    ])
                except Exception as e:
                    results["errors"].append(f"Source {source.id}: {str(e)}")
                    log.error("poll_source_error", source_id=source.id, error=str(e))

    except Exception as e:
        log.error("poll_all_sources_failed", error=str(e))
        results["errors"].append(str(e))

    log.info("poll_all_sources_completed", **results)
    return results


async def poll_kb_sources(kb_id: str) -> list[DocumentChange]:
    """Poll all data sources for a specific knowledge base.

    Args:
        kb_id: Knowledge base ID.

    Returns:
        List of all detected changes.
    """
    all_changes = []

    try:
        async for session in get_session():
            sources = await list_data_sources(session, kb_id=kb_id, enabled_only=True)
            classifier = get_change_classifier()

            for source in sources:
                changes = await poll_data_source(
                    session, source, classifier, create_entries=True,
                )
                all_changes.extend(changes)

    except Exception as e:
        log.error("poll_kb_sources_failed", kb_id=kb_id, error=str(e))

    return all_changes
