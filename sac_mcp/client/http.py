"""Async HTTP client for SAP Analytics Cloud.

A single :class:`SACClient` instance is shared by every tool. It handles:

* OAuth bearer injection (via :class:`OAuthTokenProvider`)
* CSRF token fetch + refresh on 403
* Retry with exponential backoff on 429/5xx
* Pagination over OData ``@odata.nextLink`` and Public-REST ``next`` cursors
* Token-bucket rate limiting
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Mapping

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from sac_mcp.client.auth import OAuthTokenProvider
from sac_mcp.client.csrf import CsrfTokenCache
from sac_mcp.client.errors import SACError, from_response
from sac_mcp.client.ratelimit import TokenBucket
from sac_mcp.config import Settings
from sac_mcp.logging import get_logger

_log = get_logger(__name__)

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_DEFAULT_HEADERS = {
    "Accept": "application/json",
    # Tells SAC to skip session-cookie negotiation; required for stateless clients
    # (avoids KBA 3387282 / 3566761).
    "x-sap-sac-custom-auth": "true",
}


class _RetryableHTTPStatus(Exception):
    def __init__(self, response: httpx.Response) -> None:
        self.response = response


class SACClient:
    """Thin SAC HTTP client. All tool modules call methods on this object."""

    def __init__(
        self,
        settings: Settings,
        *,
        http: httpx.AsyncClient | None = None,
        token_provider: OAuthTokenProvider | None = None,
    ) -> None:
        self._settings = settings
        self._http = http or httpx.AsyncClient(
            timeout=settings.sac_request_timeout,
            http2=True,
            base_url=settings.tenant_url_str,
        )
        self._owns_http = http is None
        self._tokens = token_provider or OAuthTokenProvider(settings, self._http)
        self._csrf = CsrfTokenCache(self._fetch_csrf)
        self._bucket = TokenBucket(rate=settings.sac_max_rps)

    # -- lifecycle -----------------------------------------------------

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> "SACClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # -- core request --------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        content: bytes | str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Execute one request with auth, CSRF, retry & rate-limit applied."""

        method = method.upper()
        attempts = max(1, self._settings.sac_max_retries + 1)

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(attempts),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
                retry=retry_if_exception_type((_RetryableHTTPStatus, httpx.TransportError)),
                reraise=True,
            ):
                with attempt:
                    return await self._send_once(method, path, params, json, content, headers)
        except RetryError as exc:  # pragma: no cover - tenacity shouldn't reach here with reraise
            raise exc.last_attempt.exception()  # type: ignore[misc]
        raise RuntimeError("unreachable")

    async def _send_once(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None,
        json: Any | None,
        content: bytes | str | None,
        headers: Mapping[str, str] | None,
    ) -> httpx.Response:
        await self._bucket.acquire()

        merged: dict[str, str] = dict(_DEFAULT_HEADERS)
        if headers:
            merged.update(headers)
        merged["Authorization"] = f"Bearer {await self._tokens.get_token()}"

        if method in _WRITE_METHODS:
            merged["x-csrf-token"] = await self._csrf.get()

        _log.debug("sac.request", method=method, path=path, params=params)

        response = await self._http.request(
            method, path, params=params, json=json, content=content, headers=merged
        )

        # 401 -> bad token, refresh once and retry
        if response.status_code == 401:
            await self._tokens.invalidate()
            merged["Authorization"] = f"Bearer {await self._tokens.get_token()}"
            response = await self._http.request(
                method, path, params=params, json=json, content=content, headers=merged
            )

        # 403 with CSRF hint -> refresh CSRF and retry once
        if (
            response.status_code == 403
            and method in _WRITE_METHODS
            and "csrf" in (response.headers.get("x-csrf-token", "") + " " + (response.text or "")).lower()
        ):
            await self._csrf.invalidate()
            merged["x-csrf-token"] = await self._csrf.get(force_refresh=True)
            response = await self._http.request(
                method, path, params=params, json=json, content=content, headers=merged
            )

        if response.status_code in (429, 502, 503, 504):
            raise _RetryableHTTPStatus(response)

        if response.status_code >= 400:
            raise from_response(response)

        return response

    # -- typed helpers -------------------------------------------------

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        response = await self.request("GET", path, params=params, headers=headers)
        if not response.content:
            return None
        return response.json()

    async def post_json(
        self,
        path: str,
        *,
        json: Any | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        response = await self.request("POST", path, json=json, params=params, headers=headers)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    async def put_json(self, path: str, *, json: Any) -> Any:
        response = await self.request("PUT", path, json=json)
        if not response.content:
            return None
        return response.json()

    async def patch_json(self, path: str, *, json: Any) -> Any:
        response = await self.request("PATCH", path, json=json)
        if not response.content:
            return None
        return response.json()

    async def delete(self, path: str) -> None:
        await self.request("DELETE", path)

    # -- pagination ----------------------------------------------------

    async def paginate(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        value_key: str = "value",
        max_rows: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield rows from an OData / Public REST collection.

        Follows ``@odata.nextLink`` (OData) or ``next`` (Public REST) links until
        exhausted or ``max_rows`` is reached.
        """

        next_path: str | None = path
        next_params: Mapping[str, Any] | None = params
        rows_yielded = 0
        while next_path is not None:
            payload = await self.get_json(next_path, params=next_params)
            if not isinstance(payload, dict):
                return
            rows = payload.get(value_key) or payload.get("Resources") or []
            for row in rows:
                yield row
                rows_yielded += 1
                if max_rows is not None and rows_yielded >= max_rows:
                    return

            next_link = (
                payload.get("@odata.nextLink")
                or payload.get("nextLink")
                or payload.get("next")
            )
            if not next_link:
                return
            next_path = next_link
            next_params = None  # nextLink already includes query

    # -- CSRF fetcher --------------------------------------------------

    async def _fetch_csrf(self) -> str:
        # Use a bare GET (no recursion through self.request, since we don't need
        # CSRF for GETs and want to avoid circular CSRF acquisition).
        await self._bucket.acquire()
        headers = {
            **_DEFAULT_HEADERS,
            "x-csrf-token": "fetch",
            "Authorization": f"Bearer {await self._tokens.get_token()}",
        }
        response = await self._http.get("/api/v1/csrf", headers=headers)
        if response.status_code >= 400:
            raise from_response(response)
        token = response.headers.get("x-csrf-token", "")
        if not token:
            raise SACError(
                "SAC /api/v1/csrf did not return an x-csrf-token header — verify "
                "x-sap-sac-custom-auth header and OAuth scope"
            )
        return token


@asynccontextmanager
async def sac_client(settings: Settings) -> AsyncIterator[SACClient]:
    client = SACClient(settings)
    try:
        yield client
    finally:
        await client.aclose()
