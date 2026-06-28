"""SQL query router for SAP Analytics Cloud.

Accepts a SQL-like or natural-language query and automatically routes to the
best SAC API:

* Aggregation queries with explicit aggregate functions (``SUM(col)``,
  ``COUNT(col)``, etc.) are routed to the OData Aggregation entity for
  server-side GROUP BY when no story+widget pair is provided.
* Aggregation queries with a story+widget pair prefer the Widget Query API.
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
    r"\bWHERE\s+(.+?)(?:\s+ORDER\s+BY\b|\s+TOP\b|\s+LIMIT\b|\s+GROUP\s+BY\b|$)",
    re.IGNORECASE,
)
_GROUP_BY_RE = re.compile(
    r"\bGROUP\s+BY\s+(.+?)(?:\s+(?:ORDER\s+BY|TOP|LIMIT|HAVING|WHERE)\b|$)",
    re.IGNORECASE,
)
# Captures: (op, column, alias) — alias may be empty string
_AGG_EXPR_RE = re.compile(
    r"\b(SUM|COUNT|AVG|MIN|MAX)\s*\(\s*([^)]+)\s*\)(?:\s+AS\s+(\w+))?",
    re.IGNORECASE,
)
_SQL_OP_MAP = {
    "SUM": "sum",
    "COUNT": "count",
    "AVG": "average",
    "MIN": "min",
    "MAX": "max",
}


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
        Export API for raw row data. Queries with explicit aggregate functions
        (SUM(col), COUNT(col), etc.) are routed to the OData Aggregation entity
        for server-side GROUP BY. Aggregation queries are routed to the Widget
        Query API instead if ``story_id`` and ``widget_id`` are provided.

        Args:
            model_id: The SAC model ID to query.
            query: A SQL-like query string. Examples:
                - ``"SELECT * WHERE Region eq 'EMEA' TOP 50"``
                - ``"SUM(Amount) GROUP BY Region WHERE Year eq '2024'"``
                - ``"Region eq 'EMEA' AND Product eq 'Widget'"``
            top: Default max rows for OData queries (default 200).
            entity: OData entity set for non-aggregation queries: ``FactData``,
                ``MasterData`` or ``AuditData``.
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

        if analytical:
            # Parse aggregate expressions: SUM(col), COUNT(col), AVG(col), etc.
            group_by_m = _GROUP_BY_RE.search(query)
            group_by = (
                [c.strip() for c in group_by_m.group(1).split(",") if c.strip()]
                if group_by_m
                else []
            )
            agg_matches = _AGG_EXPR_RE.findall(query)
            aggregates: list[dict[str, Any]] = []
            for op, col, alias in agg_matches:
                op_norm = _SQL_OP_MAP.get(op.upper(), op.lower())
                col_clean = col.strip()
                alias_clean = alias.strip() if alias.strip() else f"{op.capitalize()}{col_clean}"
                aggregates.append({"column": col_clean, "op": op_norm, "alias": alias_clean})

            if aggregates:
                agg_parts = ", ".join(
                    f"{a['column']} with {a['op']} as {a['alias']}"
                    for a in aggregates
                )
                if group_by:
                    apply_str = f"groupby(({','.join(group_by)}),aggregate({agg_parts}))"
                else:
                    apply_str = f"aggregate({agg_parts})"

                agg_params: dict[str, Any] = {"$apply": apply_str, "$top": str(top)}
                top_m = _TOP_RE.search(query)
                if top_m:
                    agg_params["$top"] = top_m.group(1)
                where_m = _WHERE_RE.search(query)
                if where_m:
                    agg_params["$filter"] = where_m.group(1).strip()
                orderby_m = _ORDERBY_RE.search(query)
                if orderby_m:
                    agg_params["$orderby"] = orderby_m.group(1).strip()

                agg_rows: list[dict[str, Any]] = []
                async for r in client.paginate(
                    f"/api/v1/dataexport/providers/sac/{model_id}/Aggregation",
                    params=agg_params,
                    max_rows=int(agg_params["$top"]),
                ):
                    agg_rows.append(r)
                return {"route": "aggregation", **page_envelope(compact(agg_rows))}

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
                    "Aggregation keyword detected but no explicit aggregate "
                    "functions (e.g. SUM(col), COUNT(col)) were found — fell "
                    "back to raw OData data. Use read_aggregated_data directly "
                    "for server-side GROUP BY aggregation."
                ),
                **envelope,
            }
        return {"route": "odata_export", **envelope}
