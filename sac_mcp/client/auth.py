"""2-legged OAuth (client credentials) for SAP Analytics Cloud.

A single :class:`OAuthTokenProvider` is shared across the process. Tokens are
cached in memory; refreshes happen 60 s before expiry to avoid token-stampede.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx

from sac_mcp.client.errors import SACError, from_response
from sac_mcp.config import Settings
from sac_mcp.logging import get_logger

_log = get_logger(__name__)
_REFRESH_LEEWAY_SECONDS = 60.0


@dataclass
class _CachedToken:
    access_token: str
    expires_at: float  # epoch seconds

    def is_fresh(self, leeway: float = _REFRESH_LEEWAY_SECONDS) -> bool:
        return time.time() + leeway < self.expires_at


class OAuthTokenProvider:
    """Thread-safe OAuth client_credentials token provider."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._http = http  # if None, a short-lived client is created per refresh
        self._token: _CachedToken | None = None
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        if self._token is not None and self._token.is_fresh():
            return self._token.access_token
        async with self._lock:
            if self._token is not None and self._token.is_fresh():
                return self._token.access_token
            self._token = await self._fetch()
            return self._token.access_token

    async def invalidate(self) -> None:
        async with self._lock:
            self._token = None

    async def _fetch(self) -> _CachedToken:
        token_url = f"{self._settings.auth_url_str}/oauth/token"
        data = {"grant_type": "client_credentials"}
        if self._settings.sac_oauth_scope:
            data["scope"] = self._settings.sac_oauth_scope

        auth = (
            self._settings.sac_client_id,
            self._settings.sac_client_secret.get_secret_value(),
        )
        headers = {"Accept": "application/json"}

        _log.debug("oauth.fetch", url=token_url, scope=self._settings.sac_oauth_scope)

        client = self._http
        owns_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=self._settings.sac_request_timeout)
            owns_client = True
        try:
            response = await client.post(token_url, data=data, auth=auth, headers=headers)
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code != 200:
            raise from_response(response)

        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover - defensive
            raise SACError("OAuth token response was not JSON", status_code=response.status_code) from exc

        access = payload.get("access_token")
        if not access:
            raise SACError("OAuth token response missing access_token", status_code=200,
                           details=payload)

        expires_in = float(payload.get("expires_in", 3600))
        return _CachedToken(access_token=access, expires_at=time.time() + expires_in)
