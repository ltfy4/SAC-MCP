"""``sac://catalog/models`` resource — cached list of all models."""

from __future__ import annotations

import json
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from sac_mcp.client.http import SACClient

_CACHE_TTL_SECONDS = 300.0
_cache: dict[str, Any] = {"at": 0.0, "value": None}


def register(server: FastMCP, client: SACClient) -> None:
    @server.resource("sac://catalog/models", mime_type="application/json")
    async def model_catalog() -> str:
        now = time.time()
        if _cache["value"] is not None and now - _cache["at"] < _CACHE_TTL_SECONDS:
            return json.dumps(_cache["value"], indent=2)

        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            "/api/v1/dataexport/administration/Namespaces('sac')/Providers",
            max_rows=10_000,
        ):
            rows.append(r)
        _cache["value"] = {"models": rows, "count": len(rows)}
        _cache["at"] = now
        return json.dumps(_cache["value"], indent=2)
