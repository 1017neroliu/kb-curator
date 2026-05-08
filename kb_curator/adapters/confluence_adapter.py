"""Confluence REST API v1 document source adapter (Cloud + Data Center)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from kb_curator.adapters.base import BaseDocumentSource, DocumentChange, DocumentMetadata
from kb_curator.adapters.http_mixin import HttpAdapterMixin
from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import ChangeType

log = get_logger(__name__)


class ConfluenceAdapter(HttpAdapterMixin, BaseDocumentSource):
    """Document source adapter for Confluence via the REST API v1.

    connection_config keys:
        url (str, required): Base URL (e.g. ``https://your-domain.atlassian.net``).
        username (str, required): Email (Cloud) or username (Data Center).
        api_token (str, required): API token (Cloud) or PAT (Data Center).
        auth_type (str): ``"basic"`` (default) or ``"bearer"`` for Data Center PAT.
        space_key (str | None): Confluence space key to scan. If omitted, scans all.
        cql (str | None): Custom CQL query to filter content.
        max_pages (int): Maximum pages to fetch per scan. Default ``500``.
        request_delay (float): Delay between requests. Default ``0.1``.
    """

    def __init__(
        self,
        source_id: str,
        kb_id: str,
        connection_config: dict[str, Any],
    ) -> None:
        BaseDocumentSource.__init__(self, source_id, kb_id, connection_config)

        self._base_url = connection_config["url"].rstrip("/")
        self._username = connection_config["username"]
        self._api_token = connection_config["api_token"]

        # Auth type: basic (Cloud default) or bearer (Data Center PAT)
        self._auth_type = connection_config.get("auth_type", "basic")
        if self._auth_type == "bearer":
            self._bearer_token = self._api_token
            self._password = None
        else:
            self._password = self._api_token
            self._bearer_token = None

        # Options
        self._space_key = connection_config.get("space_key")
        self._cql = connection_config.get("cql")
        self._max_pages = connection_config.get("max_pages", 500)
        self._request_delay = connection_config.get("request_delay", 0.1)
        self._timeout = 30.0

    # ------------------------------------------------------------------
    # BaseDocumentSource interface
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Verify Confluence is reachable via ``GET /rest/api/space?limit=1``."""
        try:
            resp = await self._request(
                "GET",
                f"{self._base_url}/rest/api/space",
                params={"limit": 1},
            )
            data = resp.json()
            return "results" in data
        except Exception as e:
            log.error("confluence_health_check_failed", error=str(e))
            return False

    async def list_documents(self) -> list[DocumentMetadata]:
        """List all pages in the configured space (or all spaces)."""
        documents: list[DocumentMetadata] = []
        start = 0
        limit = 50

        while True:
            params: dict[str, Any] = {
                "type": "page",
                "start": start,
                "limit": limit,
                "expand": "version",
            }
            if self._cql:
                params["cql"] = self._cql
            elif self._space_key:
                params["spaceKey"] = self._space_key

            resp = await self._request(
                "GET",
                f"{self._base_url}/rest/api/content",
                params=params,
            )
            data = resp.json()
            results = data.get("results", [])

            if not results:
                break

            for page in results:
                doc_id = f"confluence:{page['id']}"
                version = page.get("version", {})
                when_str = version.get("when", "")

                # Use title + version number for lightweight hash
                content_hash = await self.compute_content_hash(
                    f"{page['id']}:{version.get('number', 0)}:{page['title']}"
                )

                documents.append(
                    DocumentMetadata(
                        document_id=doc_id,
                        title=page["title"],
                        content_hash=content_hash,
                        modified_at=datetime.fromisoformat(when_str) if when_str else None,
                        source_url=(
                            page.get("_links", {}).get("base", self._base_url)
                            + page.get("_links", {}).get("webui", "")
                        ),
                        metadata={
                            "content_id": page["id"],
                            "version": version.get("number", 0),
                        },
                    )
                )

            # Pagination
            if data.get("last"):
                break
            start += limit

            if len(documents) >= self._max_pages:
                break

        return documents[: self._max_pages]

    async def get_content(self, document_id: str) -> str:
        """Retrieve page content as plain text.

        Args:
            document_id: Format ``confluence:{content_id}``.
        """
        content_id = document_id.split("confluence:", 1)[1]
        resp = await self._request(
            "GET",
            f"{self._base_url}/rest/api/content/{content_id}",
            params={"expand": "body.storage,version"},
        )
        data = resp.json()
        storage_html = data.get("body", {}).get("storage", {}).get("value", "")
        return self._storage_to_text(storage_html)

    async def poll(
        self,
        since: datetime | None = None,
        known_documents: dict[str, str] | None = None,
    ) -> list[DocumentChange]:
        """Poll for changes.

        If *since* is given, use CQL with ``lastModified``; otherwise, fall
        back to a full scan via :meth:`list_documents`.
        """
        known = known_documents or {}
        changes: list[DocumentChange] = []

        if since:
            changes = await self._poll_cql(since, known)
        else:
            changes = await self._poll_full_scan(known)

        return changes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _poll_cql(
        self,
        since: datetime,
        known: dict[str, str],
    ) -> list[DocumentChange]:
        """Poll using CQL with a lastModified filter."""
        changes: list[DocumentChange] = []
        start = 0
        limit = 50

        # Build CQL
        cql_parts: list[str] = ['type=page']
        if self._space_key:
            cql_parts.append(f'space="{self._space_key}"')
        cql_parts.append(f'lastModified > "{since.isoformat()}"')
        cql = " and ".join(cql_parts)

        while True:
            resp = await self._request(
                "GET",
                f"{self._base_url}/rest/api/content",
                params={
                    "cql": cql,
                    "start": start,
                    "limit": limit,
                    "expand": "version",
                },
            )
            data = resp.json()
            results = data.get("results", [])

            if not results:
                break

            for page in results:
                doc_id = f"confluence:{page['id']}"
                title = page["title"]
                version = page.get("version", {})
                content_hash = await self.compute_content_hash(
                    f"{page['id']}:{version.get('number', 0)}:{title}"
                )
                previous_hash = known.get(doc_id)
                change_type = ChangeType.POLICY_CHANGE if previous_hash else ChangeType.NEW_INFO

                if previous_hash and previous_hash == content_hash:
                    continue

                # Fetch full content
                try:
                    content = await self.get_content(doc_id)
                except Exception as e:
                    log.warning("confluence_content_fetch_failed", doc_id=doc_id, error=str(e))
                    continue

                changes.append(
                    DocumentChange(
                        document_id=doc_id,
                        title=title,
                        content_before=None,
                        content_after=content,
                        change_type=change_type,
                        source_url=(
                            page.get("_links", {}).get("base", self._base_url)
                            + page.get("_links", {}).get("webui", "")
                        ),
                        fingerprint_before=previous_hash,
                        fingerprint_after=content_hash,
                        metadata={
                            "content_id": page["id"],
                            "version": version.get("number", 0),
                        },
                    )
                )

                if len(changes) >= self._max_pages:
                    break

            if data.get("last") or len(changes) >= self._max_pages:
                break
            start += limit

        return changes

    async def _poll_full_scan(
        self,
        known: dict[str, str],
    ) -> list[DocumentChange]:
        """Full scan listing all pages and comparing hashes."""
        changes: list[DocumentChange] = []
        documents = await self.list_documents()
        current_ids: set[str] = set()

        for doc in documents:
            current_ids.add(doc.document_id)
            previous_hash = known.get(doc.document_id)

            try:
                content = await self.get_content(doc.document_id)
                content_hash = await self.compute_content_hash(content)
            except Exception as e:
                log.warning("confluence_content_fetch_failed", doc_id=doc.document_id, error=str(e))
                continue

            if previous_hash is None:
                change_type = ChangeType.NEW_INFO
            elif previous_hash != content_hash:
                change_type = ChangeType.POLICY_CHANGE
            else:
                continue  # Unchanged

            changes.append(
                DocumentChange(
                    document_id=doc.document_id,
                    title=doc.title,
                    content_before=None,
                    content_after=content,
                    change_type=change_type,
                    source_url=doc.source_url,
                    fingerprint_before=previous_hash,
                    fingerprint_after=content_hash,
                )
            )

        # Detect deleted pages
        for doc_id in known:
            if doc_id not in current_ids:
                log.info("confluence_page_deleted", document_id=doc_id)

        return changes

    @staticmethod
    def _storage_to_text(storage_html: str) -> str:
        """Convert Confluence storage-format HTML to plain text.

        Strips ``<ac:*>`` and ``<ri:*>`` macros first, then strips remaining
        HTML tags.
        """
        text = storage_html
        # Remove Confluence macros <ac:...>...</ac:...>
        text = re.sub(r"<ac:[^>]*>.*?</ac:[^>]*>", "", text, flags=re.DOTALL)
        text = re.sub(r"<ac:[^/]*/>", "", text)
        # Remove reference tags <ri:.../>
        text = re.sub(r"<ri:[^>]*/?>", "", text)
        # Convert <br> and <br/> to newlines
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        # Convert block-level tags to newlines
        for tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            text = re.sub(rf"</?{tag}[^>]*>", "\n", text, flags=re.IGNORECASE)
        # Remove remaining HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Decode common HTML entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&nbsp;", " ").replace("&quot;", '"')
        # Collapse whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()
