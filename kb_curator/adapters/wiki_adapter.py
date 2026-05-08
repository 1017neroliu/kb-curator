"""MediaWiki Action API document source adapter."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

from kb_curator.adapters.base import BaseDocumentSource, DocumentChange, DocumentMetadata
from kb_curator.adapters.http_mixin import HttpAdapterMixin
from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import ChangeType

log = get_logger(__name__)


class WikiAdapter(HttpAdapterMixin, BaseDocumentSource):
    """Document source adapter for MediaWiki instances via the Action API.

    connection_config keys:
        url (str, required): Base URL of the wiki (e.g. ``https://en.wikipedia.org``).
        api_path (str): Path to api.php. Default ``/w/api.php``.
        username (str | None): Username for Basic Auth (optional).
        password (str | None): Password for Basic Auth (optional).
        namespaces (list[int]): MediaWiki namespace IDs to scan. Default ``[0]``.
        max_pages (int): Maximum number of pages to fetch per scan. Default ``500``.
        request_delay (float): Delay between API requests in seconds. Default ``0.2``.
    """

    def __init__(
        self,
        source_id: str,
        kb_id: str,
        connection_config: dict[str, Any],
    ) -> None:
        BaseDocumentSource.__init__(self, source_id, kb_id, connection_config)

        self._base_url = connection_config["url"].rstrip("/")
        self._api_path = connection_config.get("api_path", "/w/api.php")
        self._api_url = f"{self._base_url}{self._api_path}"

        # Auth
        self._username = connection_config.get("username")
        self._password = connection_config.get("password")
        self._auth_type = "basic" if self._username and self._password else "none"
        self._bearer_token = None

        # Options
        self._namespaces = connection_config.get("namespaces", [0])
        self._max_pages = connection_config.get("max_pages", 500)
        self._request_delay = connection_config.get("request_delay", 0.2)
        self._timeout = 30.0

    # ------------------------------------------------------------------
    # BaseDocumentSource interface
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Verify the wiki API is reachable via ``action=query&meta=siteinfo``."""
        try:
            resp = await self._request(
                "GET",
                self._api_url,
                params={"action": "query", "meta": "siteinfo", "format": "json"},
            )
            data = resp.json()
            return "query" in data
        except Exception as e:
            log.error("wiki_health_check_failed", error=str(e))
            return False

    async def list_documents(self) -> list[DocumentMetadata]:
        """List all pages in configured namespaces via ``action=query&list=allpages``."""
        documents: list[DocumentMetadata] = []
        for ns in self._namespaces:
            docs = await self._list_namespace(ns)
            documents.extend(docs)
            if len(documents) >= self._max_pages:
                break
        return documents[: self._max_pages]

    async def get_content(self, document_id: str) -> str:
        """Retrieve wikitext content and convert to plain text.

        Args:
            document_id: Format ``wiki:{page_id}``.
        """
        page_id = document_id.split("wiki:", 1)[1]
        # First get the title from page_id
        resp = await self._request(
            "GET",
            self._api_url,
            params={
                "action": "query",
                "pageids": page_id,
                "format": "json",
            },
        )
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        title = None
        for pid, page_info in pages.items():
            title = page_info.get("title")
            break
        if not title:
            raise ValueError(f"Cannot resolve title for page_id={page_id}")

        # Fetch wikitext
        resp = await self._request(
            "GET",
            self._api_url,
            params={
                "action": "parse",
                "page": title,
                "prop": "wikitext",
                "format": "json",
            },
        )
        data = resp.json()
        wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
        return self._wikitext_to_text(wikitext)

    async def poll(
        self,
        since: datetime | None = None,
        known_documents: dict[str, str] | None = None,
    ) -> list[DocumentChange]:
        """Poll for changes.

        If *since* is given, use ``list=recentchanges``; otherwise, fall back
        to a full scan via :meth:`list_documents` and compare content hashes.
        """
        known = known_documents or {}
        changes: list[DocumentChange] = []

        if since:
            changes = await self._poll_recent_changes(since, known)
        else:
            changes = await self._poll_full_scan(known)

        return changes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _list_namespace(self, namespace: int) -> list[DocumentMetadata]:
        """List all pages in a single namespace, handling continuation."""
        documents: list[DocumentMetadata] = []
        apcontinue: str | None = None

        while True:
            params: dict[str, Any] = {
                "action": "query",
                "list": "allpages",
                "apnamespace": namespace,
                "aplimit": "max",
                "format": "json",
            }
            if apcontinue:
                params["apcontinue"] = apcontinue

            resp = await self._request("GET", self._api_url, params=params)
            data = resp.json()

            for page in data.get("query", {}).get("allpages", []):
                doc_id = f"wiki:{page['pageid']}"
                # Compute hash from title + pageid for lightweight metadata
                content_hash = await self.compute_content_hash(f"{page['pageid']}:{page['title']}")
                documents.append(
                    DocumentMetadata(
                        document_id=doc_id,
                        title=page["title"],
                        content_hash=content_hash,
                        source_url=f"{self._base_url}/wiki/{quote(page['title'], safe='')}",
                    )
                )

            # Continuation
            rc_continue = data.get("continue", {}).get("apcontinue")
            if not rc_continue:
                break
            apcontinue = rc_continue

            if len(documents) >= self._max_pages:
                break

        return documents

    async def _poll_recent_changes(
        self,
        since: datetime,
        known: dict[str, str],
    ) -> list[DocumentChange]:
        """Poll using ``list=recentchanges``."""
        changes: list[DocumentChange] = []
        rccontinue: str | None = None

        while True:
            params: dict[str, Any] = {
                "action": "query",
                "list": "recentchanges",
                "rcstart": since.isoformat(),
                "rclimit": "max",
                "rcnamespace": "|".join(str(ns) for ns in self._namespaces),
                "format": "json",
            }
            if rccontinue:
                params["rccontinue"] = rccontinue

            resp = await self._request("GET", self._api_url, params=params)
            data = resp.json()

            for rc in data.get("query", {}).get("recentchanges", []):
                doc_id = f"wiki:{rc['pageid']}"
                title = rc["title"]

                try:
                    content = await self.get_content(doc_id)
                    content_hash = await self.compute_content_hash(content)
                except Exception as e:
                    log.warning("wiki_content_fetch_failed", doc_id=doc_id, error=str(e))
                    continue

                previous_hash = known.get(doc_id)
                change_type = ChangeType.POLICY_CHANGE if previous_hash else ChangeType.NEW_INFO

                if previous_hash and previous_hash == content_hash:
                    continue  # No actual change

                changes.append(
                    DocumentChange(
                        document_id=doc_id,
                        title=title,
                        content_before=None,
                        content_after=content,
                        change_type=change_type,
                        source_url=f"{self._base_url}/wiki/{quote(title, safe='')}",
                        fingerprint_before=previous_hash,
                        fingerprint_after=content_hash,
                        metadata={"page_id": rc["pageid"], "rc_type": rc.get("type", "")},
                    )
                )

                if len(changes) >= self._max_pages:
                    break

            rc_continue = data.get("continue", {}).get("rccontinue")
            if not rc_continue or len(changes) >= self._max_pages:
                break

        return changes

    async def _poll_full_scan(
        self,
        known: dict[str, str],
    ) -> list[DocumentChange]:
        """Full scan by listing all pages and comparing hashes."""
        changes: list[DocumentChange] = []
        documents = await self.list_documents()
        current_ids: set[str] = set()

        for doc in documents:
            current_ids.add(doc.document_id)
            previous_hash = known.get(doc.document_id)

            # Fetch actual content for hash comparison
            try:
                content = await self.get_content(doc.document_id)
                content_hash = await self.compute_content_hash(content)
            except Exception as e:
                log.warning("wiki_content_fetch_failed", doc_id=doc.document_id, error=str(e))
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
                log.info("wiki_page_deleted", document_id=doc_id)

        return changes

    @staticmethod
    def _wikitext_to_text(wikitext: str) -> str:
        """Strip wikitext markup to produce plain text."""
        text = wikitext
        # Remove HTML comments
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        # Remove references <ref>...</ref>
        text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
        text = re.sub(r"<ref[^/]*/>", "", text)
        # Remove templates {{...}} (non-greedy, handles one level)
        text = re.sub(r"\{\{[^}]*\}\}", "", text)
        # Remove file/image links
        text = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", text, flags=re.IGNORECASE)
        # Convert internal links [[target|display]] → display
        text = re.sub(r"\[\[([^|\]]*\|)?([^\]]*)\]\]", r"\2", text)
        # Convert external links [url display] → display
        text = re.sub(r"\[https?://\S*\s+([^\]]*)\]", r"\1", text)
        text = re.sub(r"\[https?://\S*\]", "", text)
        # Remove headings markup == heading == → heading
        text = re.sub(r"^={1,6}\s*(.+?)\s*={1,6}", r"\1", text, flags=re.MULTILINE)
        # Remove bold/italic
        text = re.sub(r"'{2,5}", "", text)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Remove magic words / behavior switches
        text = re.sub(r"__\w+__", "", text)
        # Collapse whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
