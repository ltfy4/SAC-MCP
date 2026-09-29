"""SQL query router for SAP Analytics Cloud.

Accepts a SQL-like or natural-language query and automatically routes to the
best SAC API:

* Aggregation queries with explicit aggregate functions (``SUM(col)``,
  ``COUNT(col)``, etc.) go through :func:`aggregation.aggregate` — SUM is
  computed by SAC (``FactDataAggregation``), other functions client-side.
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
from sac_mcp.client.paths import des_path
from sac_mcp.tools._common import collect, compact, page_envelope, safe
from sac_mcp.tools.aggregation import aggregate

_ANALYTICAL_RE = re.compile(
    r"\b(SUM|COUNT|AVG|MIN|MAX|GROUP\s+BY|AGGREGATE)\b", re.IGNORECASE
)
_TOP_RE = re.compile(r"\b(?:TOP|LIMIT)\s+(\d+)\b", re.IGNORECASE)
_SELECT_RE = re.compile(
    r"\bSELECT\s+(.+?)(?:\s+(?:FROM|WHERE|GROUP\s+BY|ORDER\s+BY|TOP|LIMIT)\b|\s*$)",
    re.IGNORECASE,
)
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
# Entity sets as exposed by the Data Export Service (verified live: "Data" does
# not exist, fact rows live in "FactData").
_ENTITY_SET = {"FactData": "FactData", "MasterData": "MasterData", "AuditData": "AuditData"}
# Split on single-quoted literals ('' is an escaped quote) so operator
# translation never touches string values.
_QUOTED_RE = re.compile(r"('(?:[^']|'')*')")


def _is_analytical(query: str) -> bool:
    return bool(_ANALYTICAL_RE.search(query))


def _sql_filter_to_odata(text: str) -> str:
    """Translate SQL comparison/logical operators into OData v4 equivalents.

    ``Region = 'EMEA' AND Amount >= 100`` → ``Region eq 'EMEA' and Amount ge 100``.
    Already-valid OData input passes through unchanged.
    """

    out: list[str] = []
    for i, part in enumerate(_QUOTED_RE.split(text)):
        if i % 2 == 1:  # quoted literal — leave untouched
            out.append(part)
            continue
        s = part
        s = re.sub(r"!=|<>", " ne ", s)
        s = re.sub(r">=", " ge ", s)
        s = re.sub(r"<=", " le ", s)
        s = re.sub(r"=", " eq ", s)
        s = re.sub(r">", " gt ", s)
        s = re.sub(r"<", " lt ", s)
        s = re.sub(r"\b(AND|OR|NOT)\b", lambda m: m.group(1).lower(), s)
        out.append(s)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _sql_orderby_to_odata(text: str) -> str:
    """OData sort directions are lowercase; SQL habit is uppercase."""

    return re.sub(r"\b(ASC|DESC)\b", lambda m: m.group(1).lower(), text.strip())


def _parse_simple_query(query: str) -> dict[str, Any]:
    """Best-effort parse of a SQL-ish string into OData params."""

    out: dict[str, Any] = {}
    q = query.strip()

    m = _TOP_RE.search(q)
    if m:
        out["top"] = int(m.group(1))

    m = _ORDERBY_RE.search(q)
    if m:
        out["orderby"] = _sql_orderby_to_odata(m.group(1))

    m = _WHERE_RE.search(q)
    if m:
        out["filter"] = _sql_filter_to_odata(m.group(1))

    select_match = _SELECT_RE.search(q)
    if select_match:
        sel = ",".join(c.strip() for c in select_match.group(1).split(",") if c.strip())
        if sel and sel != "*":
            out["select"] = sel

    if "filter" not in out and not re.search(r"\bSELECT\b", q, re.IGNORECASE):
        # No SELECT keyword — treat the whole cleaned string as a filter.
        cleaned = _TOP_RE.sub("", q)
        cleaned = _ORDERBY_RE.sub("", cleaned).strip()
        if cleaned:
            out["filter"] = _sql_filter_to_odata(cleaned)

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
        entity_set = _ENTITY_SET.get(entity, entity)

        if analytical and story_id and widget_id:
            result = await client.get_json(
                "/api/v1/widgetquery/getWidgetData",
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
            group_by_m = _GROUP_BY_RE.search(query)
            group_by = (
                [c.strip() for c in group_by_m.group(1).split(",") if c.strip()]
                if group_by_m
                else []
            )
            aggregates: list[dict[str, Any]] = []
            for op, col, alias in _AGG_EXPR_RE.findall(query):
                op_norm = _SQL_OP_MAP.get(op.upper(), op.lower())
                col_clean = col.strip()
                aggregates.append({
                    "column": col_clean,
                    "op": op_norm,
                    "alias": alias.strip() or f"{op.capitalize()}{col_clean}",
                })

            if aggregates:
                top_m = _TOP_RE.search(query)
                where_m = _WHERE_RE.search(query)
                orderby_m = _ORDERBY_RE.search(query)
                result = await aggregate(
                    client,
                    model_id,
                    group_by,
                    aggregates,
                    filter=_sql_filter_to_odata(where_m.group(1)) if where_m else None,
                    orderby=[
                        o.strip() for o in _sql_orderby_to_odata(orderby_m.group(1)).split(",")
                    ] if orderby_m else None,
                    top=int(top_m.group(1)) if top_m else top,
                )
                return {"route": "aggregation", **result}

        parsed = _parse_simple_query(query)
        row_cap = int(parsed.get("top", top))
        params: dict[str, Any] = {}
        if "filter" in parsed:
            params["$filter"] = parsed["filter"]
        if "orderby" in parsed:
            params["$orderby"] = parsed["orderby"]

        note: str | None = None
        path = des_path(model_id, entity_set)
        if "select" in parsed:
            params["$select"] = parsed["select"]
            if entity_set == "FactData":
                # FactData rejects a $select without every key column (1402);
                # FactDataAggregation returns the projection, summed over the
                # dimensions that were left out.
                path = des_path(model_id, "FactDataAggregation")
                note = (
                    "Projected via FactDataAggregation: measures are summed over the "
                    "dimensions not listed in SELECT."
                )

        rows, more = await collect(client, path, params=params, max_rows=row_cap)
        envelope = page_envelope(compact(rows), has_more=more)
        if note:
            envelope["note"] = note
        if analytical:
            fallback = (
                "Aggregation keyword detected but no explicit aggregate functions "
                "(e.g. SUM(col), COUNT(col)) were found — returned rows without "
                "aggregating. Use read_aggregated_data for GROUP BY aggregation."
            )
            envelope["note"] = f"{fallback} {envelope['note']}" if "note" in envelope else fallback
        return {"route": "odata_export", **envelope}
