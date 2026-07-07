"""MCP tools for SAP Analytics Cloud delta/difference tracking.

Provides tools to establish a change-tracking baseline and then retrieve only
rows that changed since the last query. Uses SAC's OData v4 delta extension
(``Prefer: odata.track-changes`` plus the ``$deltatoken`` query parameter).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import compact, page_envelope, safe


def _extract_delta_token(payload: dict[str, Any]) -> tuple[str, str]:
    """Return ``(delta_token, delta_link)`` from an OData delta response."""

    link = payload.get("@odata.deltaLink") or ""
    if not link:
        return "", ""
    if "$deltatoken=" in link:
        token = link.split("$deltatoken=", 1)[1]
        # Strip any trailing query parameters
        token = token.split("&", 1)[0]
        return token, link
    qs = parse_qs(urlsplit(link).query)
    values = qs.get("$deltatoken") or qs.get("deltatoken") or []
    return (values[0] if values else ""), link


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def init_delta_tracking(
        model_id: str,
        entity: str = "Data",
        top: int = 200,
        filter: str | None = None,
    ) -> dict[str, Any]:
        """Start delta tracking for a model entity set.

        Returns the current data plus a ``delta_token``. Pass that token to
        :func:`get_delta_changes` on subsequent calls to receive only changes.

        Args:
            model_id: The SAC model (provider) ID.
            entity: OData entity set, defaults to ``Data`` (fact data).
            top: Page size cap.
            filter: Raw OData ``$filter`` expression.
        """

        params: dict[str, Any] = {"$top": top}
        if filter:
            params["$filter"] = filter

        payload = await client.get_json(
            f"/api/v1/dataexport/providers/sac/{model_id}/{entity}",
            params=params,
            headers={"Prefer": "odata.track-changes"},
        )
        if not isinstance(payload, dict):
            return {"delta_token": "", "delta_link": "", **page_envelope([])}

        rows = [r for r in (payload.get("value") or []) if isinstance(r, dict)]
        token, link = _extract_delta_token(payload)
        return {
            "delta_token": token,
            "delta_link": link,
            **page_envelope(compact(rows)),
        }

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_delta_changes(
        model_id: str,
        delta_token: str,
        entity: str = "Data",
    ) -> dict[str, Any]:
        """Get only the rows that changed since the delta token was issued."""

        payload = await client.get_json(
            f"/api/v1/dataexport/providers/sac/{model_id}/{entity}",
            params={"$deltatoken": delta_token},
        )
        if not isinstance(payload, dict):
            return {"delta_token": "", "delta_link": "", **page_envelope([])}

        rows = [r for r in (payload.get("value") or []) if isinstance(r, dict)]
        token, link = _extract_delta_token(payload)
        return {
            "delta_token": token,
            "delta_link": link,
            **page_envelope(compact(rows)),
        }
