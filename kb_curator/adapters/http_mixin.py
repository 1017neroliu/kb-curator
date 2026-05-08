"""Shared HTTP client mixin for remote document source adapters."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from kb_curator.core.logging import get_logger

log = get_logger(__name__)


class HttpAdapterMixin:
    """Mixin providing shared httpx async client, authentication, and retry logic.

    Expects the host class to set these attributes in ``__init__``:
        _base_url (str): Root URL of the remote service.
        _auth_type (str): ``"basic"`` | ``"bearer"`` | ``"none"``.
        _username (str | None): Username for Basic Auth.
        _password (str | None): Password for Basic Auth.
        _bearer_token (str | None): Bearer token string.
        _request_delay (float): Seconds to sleep between requests (rate-limit).
        _timeout (float): httpx request timeout in seconds.
    """

    _client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _build_auth(self) -> httpx.BasicAuth | None:
        """Build httpx BasicAuth if configured."""
        if self._auth_type == "basic" and self._username and self._password:
            return httpx.BasicAuth(self._username, self._password)
        return None

    def _build_headers(self) -> dict[str, str]:
        """Build default headers, injecting Bearer token when configured."""
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._auth_type == "bearer" and self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily create (and reuse) an httpx.AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                auth=self._build_auth(),
                headers=self._build_headers(),
                timeout=httpx.Timeout(self._timeout, connect=10.0),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the shared HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Request with retry / rate-limit
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        *,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute an HTTP request with retry, rate-limit, and back-off.

        Args:
            method: HTTP method (GET, POST, …).
            url: URL path (relative to _base_url).
            max_retries: Maximum number of retry attempts.
            **kwargs: Extra keyword args forwarded to httpx request.

        Returns:
            The successful httpx.Response.

        Raises:
            httpx.HTTPStatusError: On 401/403 (immediate) or after exhausting
                retries for other error statuses.
            httpx.RequestError: After exhausting retries for transport errors.
        """
        client = self._get_client()
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                # Rate-limit delay
                if self._request_delay > 0:
                    await asyncio.sleep(self._request_delay)

                resp = await client.request(method, url, **kwargs)

                # Immediate failure on auth errors
                if resp.status_code in (401, 403):
                    log.error(
                        "http_auth_error",
                        status=resp.status_code,
                        url=url,
                    )
                    resp.raise_for_status()

                # Rate-limit back-off
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", "2"))
                    log.warning(
                        "http_rate_limited",
                        url=url,
                        retry_after=retry_after,
                        attempt=attempt,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                # Other non-success → retry with back-off
                if resp.status_code >= 400:
                    log.warning(
                        "http_error_retry",
                        status=resp.status_code,
                        url=url,
                        attempt=attempt,
                    )
                    last_exc = httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                    await asyncio.sleep(2 ** attempt)
                    continue

                return resp

            except (httpx.HTTPStatusError,) as exc:
                # 401/403 already raised above – propagate immediately
                if exc.response.status_code in (401, 403):
                    raise
                last_exc = exc
                await asyncio.sleep(2 ** attempt)

            except httpx.RequestError as exc:
                log.warning(
                    "http_transport_error",
                    url=url,
                    error=str(exc),
                    attempt=attempt,
                )
                last_exc = exc
                await asyncio.sleep(2 ** attempt)

        # All retries exhausted
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"All {max_retries} retries exhausted for {method} {url}")
