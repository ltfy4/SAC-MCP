"""Delta (change-tracking) reads over the Data Export Service.

``Prefer: odata.track-changes`` on a first read makes SAC return an
``@odata.deltaLink`` such as ``.../FactData?deltaid=<uuid>`` (verified live).
Requesting that link later returns only the rows changed since, plus a new
delta link. SAC ignores the OData-standard ``$deltatoken`` parameter — sending
it returned the entire model — so the ``deltaid`` value is what we hand out.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.paths import des_path
from sac_mcp.tools._common import compact, page_envelope, safe

_TOKEN_PARAMS = ("deltaid", "$deltatoken", "deltatoken")


def _extract_delta_token(payload: dict[str, Any]) -> tuple[str, str]:
    """Return ``(delta_token, delta_link)`` from an OData delta response."""

    link = str(payload.get("@odata.deltaLink") or "")
    if not link:
        return "", ""
    query = parse_qs(urlsplit(link).query)
    for key in _TOKEN_PARAMS:
        if query.get(key):
            return query[key][0], link
    return "", link


async def _read_pages(
    client: SACClient, path: str, params: dict[str, Any], top: int, headers: dict[str, str] | None
) -> tuple[list[dict[str, Any]], bool, dict[str, Any]]:
    """Follow nextLinks until ``top`` rows; return rows, has_more and the last page."""

    rows: list[dict[str, Any]] = []
    next_path: str | None = path
    next_params: dict[str, Any] | None = params
    last: dict[str, Any] = {}
    while next_path is not None:
        payload = await client.get_json(next_path, params=next_params, headers=headers)
        if not isinstance(payload, dict):
            break
        last = payload
        rows.extend(r for r in (payload.get("value") or []) if isinstance(r, dict))
        if len(rows) > top:
            return rows[:top], True, last
        link = payload.get("@odata.nextLink")
        next_path, next_params = (str(link), None) if link else (None, None)
    return rows, False, last


async def delta_read(
    client: SACClient, model_id: str, entity: str, delta_token: str, top: int
) -> dict[str, Any]:
    """Rows changed since ``delta_token`` plus the token for the next call."""

    rows, more, last = await _read_pages(
        client, des_path(model_id, entity), {"deltaid": delta_token}, top, None
    )
    token, link = _extract_delta_token(last)
    env = page_envelope(compact(rows), has_more=more)
    if more:
        env["hint"] = (
            "More changes than top — raise top to read them all before using the new "
            "delta_token, or rows will be missed."
        )
    return {"delta_token": token, "delta_link": link, **env}


def register(server: FastMCP, client: SACClient) -> None:
    read = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

    @server.tool(annotations=read)
    @safe
    async def init_delta_tracking(
        model_id: str,
        entity: str = "FactData",
        top: int = 200,
        filter: str | None = None,
    ) -> dict[str, Any]:
        """Start change tracking on a model entity set and get a ``delta_token``.

        Returns the first ``top`` current rows plus ``delta_token``. Pass the
        token to ``get_delta_changes`` later to receive only what changed.

        Args:
            model_id: The model (provider) ID.
            entity: Entity set to track (default ``FactData``).
            top: Maximum current rows to return with the baseline (default 200).
            filter: Optional OData ``$filter`` limiting what is tracked.
        """

        params: dict[str, Any] = {}
        if filter:
            params["$filter"] = filter
        rows, more, last = await _read_pages(
            client,
            des_path(model_id, entity),
            params,
            top,
            {"Prefer": "odata.track-changes"},
        )
        token, link = _extract_delta_token(last)
        env = page_envelope(compact(rows), has_more=more)
        if not token:
            env["hint"] = "SAC returned no delta link — change tracking may be unavailable here."
        return {"delta_token": token, "delta_link": link, **env}

    @server.tool(annotations=read)
    @safe
    async def get_delta_changes(
        model_id: str,
        delta_token: str,
        entity: str = "FactData",
        top: int = 1000,
    ) -> dict[str, Any]:
        """Return only the rows changed since ``delta_token`` was issued.

        Args:
            model_id: The model (provider) ID.
            delta_token: Token from ``init_delta_tracking`` or a previous call.
            entity: Entity set that was tracked (default ``FactData``).
            top: Maximum changed rows to return (default 1000).

        Returns rows plus a fresh ``delta_token`` for the next call.
        """

        return await delta_read(client, model_id, entity, delta_token, top)
