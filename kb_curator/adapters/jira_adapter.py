"""Jira REST API v2 document source adapter (Cloud + Data Center)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from kb_curator.adapters.base import BaseDocumentSource, DocumentChange, DocumentMetadata
from kb_curator.adapters.http_mixin import HttpAdapterMixin
from kb_curator.core.logging import get_logger
from kb_curator.models.schemas import ChangeType

log = get_logger(__name__)


class JiraAdapter(HttpAdapterMixin, BaseDocumentSource):
    """Document source adapter for Jira via the REST API v2.

    Each Jira issue is treated as a "document" comprising its title, metadata,
    description, and optionally its comments.

    connection_config keys:
        url (str, required): Base URL (e.g. ``https://your-domain.atlassian.net``).
        username (str, required): Email (Cloud) or username (Data Center).
        api_token (str, required): API token (Cloud) or PAT (Data Center).
        auth_type (str): ``"basic"`` (default) or ``"bearer"`` for Data Center PAT.
        project_key (str | None): Jira project key to filter (e.g. ``"PROJ"``).
        jql (str | None): Custom JQL query. Overrides project_key if both set.
        max_issues (int): Maximum issues to fetch per scan. Default ``200``.
        include_comments (bool): Include issue comments in content. Default ``True``.
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

        # Auth
        self._auth_type = connection_config.get("auth_type", "basic")
        if self._auth_type == "bearer":
            self._bearer_token = self._api_token
            self._password = None
        else:
            self._password = self._api_token
            self._bearer_token = None

        # Options
        self._project_key = connection_config.get("project_key")
        self._jql = connection_config.get("jql")
        self._max_issues = connection_config.get("max_issues", 200)
        self._include_comments = connection_config.get("include_comments", True)
        self._request_delay = connection_config.get("request_delay", 0.1)
        self._timeout = 30.0

    # ------------------------------------------------------------------
    # BaseDocumentSource interface
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """Verify Jira is reachable via ``GET /rest/api/2/myself``."""
        try:
            resp = await self._request(
                "GET",
                f"{self._base_url}/rest/api/2/myself",
            )
            data = resp.json()
            return "name" in data or "displayName" in data
        except Exception as e:
            log.error("jira_health_check_failed", error=str(e))
            return False

    async def list_documents(self) -> list[DocumentMetadata]:
        """List issues matching the configured JQL / project key."""
        documents: list[DocumentMetadata] = []
        start_at = 0
        max_results = 50

        while True:
            jql = self._build_jql()
            resp = await self._request(
                "GET",
                f"{self._base_url}/rest/api/2/search",
                params={
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": max_results,
                    "fields": "summary,updated",
                },
            )
            data = resp.json()
            issues = data.get("issues", [])

            if not issues:
                break

            for issue in issues:
                key = issue["key"]
                doc_id = f"jira:{key}"
                fields = issue.get("fields", {})
                updated = fields.get("updated", "")
                summary = fields.get("summary", key)

                content_hash = await self.compute_content_hash(f"{key}:{updated}")

                documents.append(
                    DocumentMetadata(
                        document_id=doc_id,
                        title=f"[{key}] {summary}",
                        content_hash=content_hash,
                        modified_at=datetime.fromisoformat(updated.rstrip("Z")) if updated else None,
                        source_url=f"{self._base_url}/browse/{key}",
                        metadata={"issue_key": key, "updated": updated},
                    )
                )

            total = data.get("total", 0)
            start_at += len(issues)

            if start_at >= total or len(documents) >= self._max_issues:
                break

        return documents[: self._max_issues]

    async def get_content(self, document_id: str) -> str:
        """Retrieve an issue's full content as markdown text.

        Args:
            document_id: Format ``jira:{ISSUE-KEY}``.
        """
        issue_key = document_id.split("jira:", 1)[1]
        resp = await self._request(
            "GET",
            f"{self._base_url}/rest/api/2/issue/{issue_key}",
        )
        data = resp.json()

        comments: list[dict] = []
        if self._include_comments:
            try:
                comments_resp = await self._request(
                    "GET",
                    f"{self._base_url}/rest/api/2/issue/{issue_key}/comment",
                )
                comments = comments_resp.json().get("comments", [])
            except Exception as e:
                log.warning("jira_comments_fetch_failed", issue_key=issue_key, error=str(e))

        return self._issue_to_content(data, comments)

    async def poll(
        self,
        since: datetime | None = None,
        known_documents: dict[str, str] | None = None,
    ) -> list[DocumentChange]:
        """Poll for changes.

        If *since* is given, append an ``updated >=`` clause to the JQL;
        otherwise, perform a full scan.
        """
        known = known_documents or {}
        changes: list[DocumentChange] = []

        if since:
            changes = await self._poll_jql(since, known)
        else:
            changes = await self._poll_full_scan(known)

        return changes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_jql(self, since: datetime | None = None) -> str:
        """Build a JQL string from config + optional *since* filter."""
        parts: list[str] = []

        if self._jql:
            parts.append(self._jql)
        elif self._project_key:
            parts.append(f"project={self._project_key}")

        if since:
            parts.append(f'updated>="{since.isoformat()}"')

        return " and ".join(parts) if parts else "order by updated desc"

    async def _poll_jql(
        self,
        since: datetime,
        known: dict[str, str],
    ) -> list[DocumentChange]:
        """Poll using JQL with an ``updated`` filter."""
        changes: list[DocumentChange] = []
        start_at = 0
        max_results = 50

        while True:
            jql = self._build_jql(since)
            resp = await self._request(
                "GET",
                f"{self._base_url}/rest/api/2/search",
                params={
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": max_results,
                    "fields": "summary,updated",
                },
            )
            data = resp.json()
            issues = data.get("issues", [])

            if not issues:
                break

            for issue in issues:
                key = issue["key"]
                doc_id = f"jira:{key}"
                fields = issue.get("fields", {})
                updated = fields.get("updated", "")
                content_hash = await self.compute_content_hash(f"{key}:{updated}")

                previous_hash = known.get(doc_id)
                change_type = ChangeType.POLICY_CHANGE if previous_hash else ChangeType.NEW_INFO

                if previous_hash and previous_hash == content_hash:
                    continue

                # Fetch full content
                try:
                    content = await self.get_content(doc_id)
                except Exception as e:
                    log.warning("jira_content_fetch_failed", doc_id=doc_id, error=str(e))
                    continue

                changes.append(
                    DocumentChange(
                        document_id=doc_id,
                        title=f"[{key}] {fields.get('summary', key)}",
                        content_before=None,
                        content_after=content,
                        change_type=change_type,
                        source_url=f"{self._base_url}/browse/{key}",
                        fingerprint_before=previous_hash,
                        fingerprint_after=content_hash,
                        metadata={"issue_key": key, "updated": updated},
                    )
                )

                if len(changes) >= self._max_issues:
                    break

            total = data.get("total", 0)
            start_at += len(issues)

            if start_at >= total or len(changes) >= self._max_issues:
                break

        return changes

    async def _poll_full_scan(
        self,
        known: dict[str, str],
    ) -> list[DocumentChange]:
        """Full scan listing all issues and comparing hashes."""
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
                log.warning("jira_content_fetch_failed", doc_id=doc.document_id, error=str(e))
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

        # Detect deleted issues
        for doc_id in known:
            if doc_id not in current_ids:
                log.info("jira_issue_deleted", document_id=doc_id)

        return changes

    def _issue_to_content(
        self,
        issue: dict[str, Any],
        comments: list[dict[str, Any]],
    ) -> str:
        """Convert a Jira issue JSON payload to a markdown-formatted string."""
        fields = issue.get("fields", {})
        key = issue.get("key", "")
        parts: list[str] = []

        # Header
        parts.append(f"# [{key}] {fields.get('summary', '')}")

        # Metadata
        status = (fields.get("status") or {}).get("name", "")
        issue_type = (fields.get("issuetype") or {}).get("name", "")
        priority = (fields.get("priority") or {}).get("name", "")
        assignee = (fields.get("assignee") or {}).get("displayName", "Unassigned")
        reporter = (fields.get("reporter") or {}).get("displayName", "")
        created = fields.get("created", "")
        updated = fields.get("updated", "")

        parts.append("")
        meta_items = [f"**Type**: {issue_type}"]
        if status:
            meta_items.append(f"**Status**: {status}")
        if priority:
            meta_items.append(f"**Priority**: {priority}")
        meta_items.append(f"**Assignee**: {assignee}")
        if reporter:
            meta_items.append(f"**Reporter**: {reporter}")
        if created:
            meta_items.append(f"**Created**: {created}")
        if updated:
            meta_items.append(f"**Updated**: {updated}")
        parts.append(" | ".join(meta_items))

        # Description
        parts.append("")
        parts.append("## Description")
        description = fields.get("description")
        if description is None:
            parts.append("_No description._")
        elif isinstance(description, str):
            parts.append(description)
        elif isinstance(description, dict):
            # Atlassian Document Format (ADF)
            parts.append(self._adf_to_text(description))
        else:
            parts.append(str(description))

        # Comments
        if self._include_comments and comments:
            parts.append("")
            parts.append("## Comments")
            for comment in comments:
                author = (comment.get("author") or {}).get("displayName", "Unknown")
                created_c = comment.get("created", "")
                body = comment.get("body", "")
                if isinstance(body, dict):
                    body = self._adf_to_text(body)
                parts.append(f"**{author}** ({created_c}):")
                parts.append(str(body))
                parts.append("")

        return "\n".join(parts)

    @staticmethod
    def _adf_to_text(node: dict[str, Any]) -> str:
        """Recursively extract plain text from an Atlassian Document Format node."""
        if not isinstance(node, dict):
            return str(node)

        node_type = node.get("type", "")
        text = node.get("text", "")

        # Text leaf
        if node_type == "text":
            return text

        # Content array
        content = node.get("content", [])
        parts: list[str] = [JiraAdapter._adf_to_text(child) for child in content]

        result = "".join(parts)

        # Add newlines for block-level nodes
        if node_type in ("paragraph", "heading", "codeBlock", "blockquote", "listItem", "rule"):
            result += "\n"
        if node_type == "bulletList" or node_type == "orderedList":
            result += "\n"

        return result
