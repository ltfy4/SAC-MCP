"""SQL query router for SAP Analytics Cloud.

Accepts a SQL-like or natural-language query and automatically routes to the
best SAC API:

* Aggregation queries (``SUM``, ``COUNT``, ``GROUP BY``) prefer the Widget
  Query API when a story+widget pair is provided.
* Everything else (``SELECT``/``WHERE``/``ORDER BY``, raw OData filters) goes
  to the OData Data Export API.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import compact, page_envelope, safe

_ANALYTICAL_RE = re.compile(
    r"\b(SUM|COUNT|AVG|MIN|MAX|GROUP\s+BY|AGGREGATE)\b", re.IGNORECASE
)
_TOP_RE = re.compile(r"\b(?:TOP|LIMIT)\s+(\d+)\b", re.IGNORECASE)
_SELECT_RE = re.compile(r"\bSELECT\s+(.+?)\s+(?:FROM|WHERE|ORDER\s+BY|TOP|LIMIT|$)", re.IGNORECASE)
_ORDERBY_RE = re.compile(
    r"\bORDER\s+BY\s+(.+?)(?:\s+TOP\b|\s+LIMIT\b|$)", re.IGNORECASE
)
_WHERE_RE = re.compile(
    r"\bWHERE\s+(.+?)(?:\s+ORDER\s+BY\b|\s+TOP\b|\s+LIMIT\b|$)", re.IGNORECASE
)


def _is_analytical(query: str) -> bool:
    return bool(_ANALYTICAL_RE.search(query))


def _parse_simple_query(query: str) -> dict[str, Any]:
    """Best-effort parse of a SQL-ish string into OData params."""

    out: dict[str, Any] = {}
    q = query.strip()

    m = _TOP_RE.search(q)
    if m:
        out["top"] = int(m.group(1))

    m = _ORDERBY_RE.search(q)
    if m:
        out["orderby"] = m.group(1).strip()

    m = _WHERE_RE.search(q)
    if m:
        out["filter"] = m.group(1).strip()

    select_match = _SELECT_RE.search(q)
    if select_match:
        sel = select_match.group(1).strip()
        if sel and sel != "*":
            out["select"] = sel

    if "filter" not in out and not re.search(r"\bSELECT\b", q, re.IGNORECASE):
        # No SELECT keyword — treat the whole cleaned string as a filter.
        cleaned = _TOP_RE.sub("", q)
        cleaned = _ORDERBY_RE.sub("", cleaned).strip()
        if cleaned:
            out["filter"] = cleaned

    return out


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def sql_query(
        model_id: str,
        query: str,
        top: int = 200,
        entity: Literal["FactData", "MasterData", "AuditData"] = "FactData",
        story_id: str | None = None,
        widget_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a query against a SAC model, automatically choosing the best API.

        Simple queries (SELECT, WHERE, ORDER BY) are routed to the OData Data
        Export API for raw row data. Queries with aggregations (SUM, COUNT,
        GROUP BY) are routed to the Widget Query API if ``story_id`` and
        ``widget_id`` are provided, otherwise fall back to OData with a note.

        Args:
            model_id: The SAC model ID to query.
            query: A SQL-like query string. Examples:
                - ``"SELECT * WHERE Region eq 'EMEA' TOP 50"``
                - ``"SUM(Amount) GROUP BY Region WHERE Year eq '2024'"``
                - ``"Region eq 'EMEA' AND Product eq 'Widget'"``
            top: Default max rows for OData queries (default 200).
            entity: OData entity set: ``FactData``, ``MasterData`` or ``AuditData``.
            story_id: SAC story ID (required for Widget Query routing).
            widget_id: Widget technical name (required for Widget Query routing).
        """

        analytical = _is_analytical(query)
        odata_path = f"/api/v1/dataexport/providers/sac/{model_id}/{entity}"

        if analytical and story_id and widget_id:
            result = await client.get_json(
                "/widgetquery/getWidgetData",
                params={
                    "storyId": story_id,
                    "widgetId": widget_id,
                    "type": "kpiTile",
                },
            )
            payload: dict[str, Any] = (
                result if isinstance(result, dict) else {"data": result}
            )
            return {"route": "widget_query", **payload}

        parsed = _parse_simple_query(query)
        params: dict[str, Any] = {"$top": parsed.get("top", top)}
        if "filter" in parsed:
            params["$filter"] = parsed["filter"]
        if "select" in parsed:
            params["$select"] = parsed["select"]
        if "orderby" in parsed:
            params["$orderby"] = parsed["orderby"]

        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            odata_path, params=params, max_rows=int(params["$top"])
        ):
            rows.append(r)

        envelope = page_envelope(compact(rows))
        if analytical:
            return {
                "route": "odata_export",
                "note": (
                    "Aggregation detected but no story_id/widget_id provided — "
                    "falling back to OData raw data. Provide story_id and "
                    "widget_id to use the Widget Query API for server-side "
                    "aggregation."
                ),
                **envelope,
            }
        return {"route": "odata_export", **envelope}
