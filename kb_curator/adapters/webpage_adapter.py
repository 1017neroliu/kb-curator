"""Generic webpage scraping document source adapter."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from kb_curator.adapters.base import BaseDocumentSource, DocumentChange, DocumentMetadata
from kb_curator.adapters.http_mixin import HttpAdapterMixin
from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import ChangeType

log = get_logger(__name__)

# Browser-like User-Agent to avoid being blocked by anti-bot systems
_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class WebpageAdapter(HttpAdapterMixin, BaseDocumentSource):
    """Document source adapter for scraping generic web pages.

    connection_config keys:
        urls (list[str], required): List of webpage URLs to scrape.
        css_selector (str | None): CSS selector to extract a specific region
            (e.g. ``article``, ``.content``, ``#main``).
        include_links (bool): Whether to follow same-domain links found on the
            pages. Default ``False``.
        max_pages (int): Maximum number of pages to fetch per scan. Default ``50``.
        request_delay (float): Delay between requests in seconds. Default ``0.5``.
        timeout (float): HTTP request timeout in seconds. Default ``30.0``.
        cookies (dict[str, str] | None): Cookies to send with each request.
            Useful for sites that require login (e.g. Zhihu).
    """

    def __init__(
        self,
        source_id: str,
        kb_id: str,
        connection_config: dict[str, Any],
    ) -> None:
        BaseDocumentSource.__init__(self, source_id, kb_id, connection_config)

        self._urls: list[str] = connection_config["urls"]
        self._css_selector: str | None = connection_config.get("css_selector")
        self._include_links: bool = connection_config.get("include_links", False)
        self._max_pages: int = connection_config.get("max_pages", 50)
        self._request_delay: float = connection_config.get("request_delay", 0.5)
        self._timeout: float = connection_config.get("timeout", 30.0)
        self._cookies: dict[str, str] | None = connection_config.get("cookies")

        # HttpAdapterMixin expects these attributes
        self._base_url = ""
        self._auth_type = "none"
        self._username = None
        self._password = None
        self._bearer_token = None

    # ------------------------------------------------------------------
    # Override headers for web scraping (browser-like)
    # ------------------------------------------------------------------

    def _build_headers(self) -> dict[str, str]:
        """Build browser-like headers for web scraping."""
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "User-Agent": _DEFAULT_UA,
        }

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily create (and reuse) an httpx.AsyncClient with browser headers."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._build_headers(),
                cookies=self._cookies or None,
                timeout=httpx.Timeout(self._timeout, connect=10.0),
                follow_redirects=True,
            )
        return self._client

    # ------------------------------------------------------------------
    # Helper: build a short, stable document ID from a URL
    # ------------------------------------------------------------------

    @staticmethod
    def _url_to_doc_id(url: str) -> str:
        """Generate a document ID from a URL: ``webpage:{sha256[:12]}``."""
        digest = hashlib.sha256(url.encode()).hexdigest()[:12]
        return f"webpage:{digest}"

    # ------------------------------------------------------------------
    # HTML → plain text
    # ------------------------------------------------------------------

    def _extract_main_content(self, html: str, url: str) -> tuple[str, str]:
        """Extract title and main text content from raw HTML.

        Returns:
            ``(title, text)`` tuple.
        """
        soup = BeautifulSoup(html, "html.parser")

        # Remove noise elements
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # If css_selector is specified, narrow down to matching elements
        if self._css_selector:
            selected = soup.select(self._css_selector)
            if selected:
                # Merge all matched elements
                container = BeautifulSoup("", "html.parser")
                for el in selected:
                    container.append(el)
                soup = container

        # Title: prefer <title> tag
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else urlparse(url).path

        # Extract text
        text = soup.get_text(separator="\n")
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Strip leading/trailing whitespace per line
        lines = [line.strip() for line in text.splitlines()]
        text = "\n".join(line for line in lines if line)

        return title, text

    # ------------------------------------------------------------------
    # Same-domain link filtering
    # ------------------------------------------------------------------

    @staticmethod
    def _should_follow_link(link: str, base_url: str) -> bool:
        """Return True if *link* belongs to the same domain as *base_url*."""
        try:
            link_parsed = urlparse(link)
            base_parsed = urlparse(base_url)
            return link_parsed.netloc == base_parsed.netloc
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Fetch a single page
    # ------------------------------------------------------------------

    async def _fetch_page(self, url: str) -> str | None:
        """GET a single URL and return its HTML body, or None on failure.

        Uses the httpx client directly (bypasses mixin _request) so that
        403 responses are treated as a fetch failure rather than an auth error.
        """
        try:
            import asyncio

            if self._request_delay > 0:
                await asyncio.sleep(self._request_delay)

            client = self._get_client()
            resp = await client.get(url)

            if resp.status_code >= 400:
                log.warning(
                    "webpage_fetch_status_error",
                    url=url,
                    status=resp.status_code,
                )
                return None

            return resp.text
        except Exception as e:
            log.warning("webpage_fetch_failed", url=url, error=str(e))
            return None

    # ------------------------------------------------------------------
    # Discover all URLs to scrape (including followed links)
    # ------------------------------------------------------------------

    async def _discover_urls(self) -> list[str]:
        """Return the full list of URLs to scrape, respecting max_pages."""
        seen: set[str] = set()
        queue: list[str] = list(self._urls)
        result: list[str] = []

        while queue and len(result) < self._max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            result.append(url)

            # If link following is enabled, extract same-domain links
            if self._include_links and len(result) < self._max_pages:
                html = await self._fetch_page(url)
                if html:
                    soup = BeautifulSoup(html, "html.parser")
                    for a_tag in soup.find_all("a", href=True):
                        href = a_tag["href"]
                        # Resolve relative URLs
                        full_url = urljoin(url, href)
                        # Remove fragment
                        full_url = full_url.split("#")[0]
                        if full_url not in seen and self._should_follow_link(full_url, url):
                            queue.append(full_url)

        return result[: self._max_pages]

    # ------------------------------------------------------------------
    # BaseDocumentSource interface
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """GET the first URL; any response (even 403) means the host is reachable.

        Many websites return 403 for HEAD requests or bot-like User-Agents,
        but still serve content for full GET requests with browser headers.
        We only report unhealthy on transport errors (DNS, timeout, etc.).
        """
        if not self._urls:
            return False
        try:
            client = self._get_client()
            resp = await client.get(self._urls[0])
            # Any HTTP response (even 4xx) means the server is reachable
            return True
        except Exception as e:
            log.error("webpage_health_check_failed", error=str(e))
            return False

    async def list_documents(self) -> list[DocumentMetadata]:
        """List all pages with their metadata and content hashes."""
        urls = await self._discover_urls()
        documents: list[DocumentMetadata] = []

        for url in urls:
            html = await self._fetch_page(url)
            if html is None:
                continue

            title, text = self._extract_main_content(html, url)
            content_hash = await self.compute_content_hash(text)

            documents.append(
                DocumentMetadata(
                    document_id=self._url_to_doc_id(url),
                    title=title,
                    content_hash=content_hash,
                    source_url=url,
                    metadata={"url": url},
                )
            )

        return documents

    async def get_content(self, document_id: str) -> str:
        """Retrieve full text content for a document by its ID.

        Args:
            document_id: Format ``webpage:{sha256[:12]}``.
        """
        # Find the URL from known URLs by matching doc_id
        for url in await self._discover_urls():
            if self._url_to_doc_id(url) == document_id:
                html = await self._fetch_page(url)
                if html:
                    _, text = self._extract_main_content(html, url)
                    return text
        raise ValueError(f"Document not found: {document_id}")

    async def poll(
        self,
        since: datetime | None = None,
        known_documents: dict[str, str] | None = None,
    ) -> list[DocumentChange]:
        """Re-scrape all URLs and detect changes by comparing content hashes."""
        known = known_documents or {}
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
                log.warning("webpage_content_fetch_failed", doc_id=doc.document_id, error=str(e))
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
                    metadata={"url": doc.source_url},
                )
            )

        # Detect removed pages
        for doc_id in known:
            if doc_id not in current_ids:
                log.info("webpage_removed", document_id=doc_id)

        return changes
