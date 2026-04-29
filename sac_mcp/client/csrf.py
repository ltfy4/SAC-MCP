"""CSRF token cache for SAC write operations.

SAC requires an ``x-csrf-token`` header for any non-GET request. Tokens are
fetched via ``GET /api/v1/csrf`` with header ``x-csrf-token: fetch`` and reused
until the server returns 403 with ``x-csrf-token: required`` (typically after
~30 minutes).
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from sac_mcp.client.errors import SACError
from sac_mcp.logging import get_logger

_log = get_logger(__name__)


class CsrfTokenCache:
    """Caches a single CSRF token; refresh is delegated to a callable."""

    def __init__(self, fetcher: Callable[[], Awaitable[str]]) -> None:
        self._fetcher = fetcher
        self._token: str | None = None
        self._lock = asyncio.Lock()

    async def get(self, *, force_refresh: bool = False) -> str:
        if self._token is not None and not force_refresh:
            return self._token
        async with self._lock:
            if self._token is not None and not force_refresh:
                return self._token
            _log.debug("csrf.fetch", force=force_refresh)
            token = await self._fetcher()
            if not token:
                raise SACError("SAC did not return an x-csrf-token header on /api/v1/csrf")
            self._token = token
            return token

    async def invalidate(self) -> None:
        async with self._lock:
            self._token = None
