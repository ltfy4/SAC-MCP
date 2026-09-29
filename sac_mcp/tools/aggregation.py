"""Aggregation over the Data Export Service.

Verified on a live tenant:

* ``FactDataAggregation`` with ``$select=<dimensions>,<measures>`` returns one
  row per combination of the selected dimensions, with each measure aggregated
  server-side by its own aggregation (SUM for amounts). ``$filter``,
  ``$orderby`` (measures too) and ``$top`` work.
* ``$apply`` (``groupby``/``aggregate``) is **silently ignored** — SAC returns
  leaf rows. Tools must never present those as aggregates.

So ``sum`` runs server-side, while ``average``/``min``/``max``/``count``/
``countdistinct`` are computed here over ``FactData`` rows (at most
``max_scan_rows``; the result says how many were scanned).
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.paths import des_path
from sac_mcp.tools._common import collect, page_envelope, safe

_VALID_OPS = frozenset({"sum", "average", "min", "max", "countdistinct", "count"})
DEFAULT_MAX_SCAN_ROWS = 50_000


def _validate(aggregates: list[dict[str, Any]]) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for agg in aggregates:
        op = str(agg.get("op", "")).lower()
        if op not in _VALID_OPS:
            raise ValueError(
                f"Invalid aggregation operator {op!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_OPS))}"
            )
        column = str(agg.get("column") or "").strip()
        if not column:
            raise ValueError("Every aggregate needs a 'column' (a measure name)")
        alias = str(agg.get("alias") or f"{op.capitalize()}{column}").strip()
        specs.append({"column": column, "op": op, "alias": alias})
    if not specs:
        raise ValueError("Provide at least one aggregate")
    return specs


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _apply(op: str, values: list[Any]) -> Any:
    present = [v for v in values if v is not None]
    if op == "count":
        return len(present)
    if op == "countdistinct":
        return len({str(v) for v in present})
    nums = [n for n in (_num(v) for v in present) if n is not None]
    if not nums:
        return None
    if op == "sum":
        return sum(nums)
    if op == "average":
        return sum(nums) / len(nums)
    return min(nums) if op == "min" else max(nums)


def _sort_key(value: Any) -> tuple[int, float, str]:
    number = _num(value)
    return (0, number, "") if number is not None else (1, 0.0, str(value))


def _sort(rows: list[dict[str, Any]], orderby: list[str]) -> None:
    """Sort in place by ``["col desc", ...]``; missing values always go last."""

    for item in reversed(orderby):  # stable sort, last key first
        col, _, direction = item.strip().partition(" ")
        present = [r for r in rows if r.get(col) is not None]
        missing = [r for r in rows if r.get(col) is None]
        present.sort(key=lambda r: _sort_key(r[col]), reverse=direction.strip().lower() == "desc")
        rows[:] = present + missing


async def aggregate(
    client: SACClient,
    model_id: str,
    group_by: list[str],
    aggregates: list[dict[str, Any]],
    *,
    filter: str | None = None,
    orderby: list[str] | None = None,
    top: int = 200,
    max_scan_rows: int = DEFAULT_MAX_SCAN_ROWS,
) -> dict[str, Any]:
    """Aggregate ``aggregates`` grouped by ``group_by``; see module docstring."""

    specs = _validate(aggregates)
    dims = [g.strip() for g in group_by if g and g.strip()]
    alias_to_column = {s["alias"]: s["column"] for s in specs}
    order = [o.strip() for o in (orderby or []) if o and o.strip()]

    if all(s["op"] == "sum" for s in specs):
        measures = list(dict.fromkeys(s["column"] for s in specs))
        params: dict[str, Any] = {"$select": ",".join(dims + measures)}
        if filter:
            params["$filter"] = filter
        if order:
            server_order = []
            for item in order:
                col, _, direction = item.partition(" ")
                server_order.append(f"{alias_to_column.get(col, col)} {direction}".strip())
            params["$orderby"] = ",".join(server_order)
        raw, more = await collect(
            client, des_path(model_id, "FactDataAggregation"), params=params, max_rows=top
        )
        rows = []
        for r in raw:
            row = {d: r.get(d) for d in dims}
            row.update({s["alias"]: r.get(s["column"]) for s in specs})
            rows.append(row)
        return {**page_envelope(rows, has_more=more), "aggregation": "server"}

    params = {"$filter": filter} if filter else {}
    raw, truncated = await collect(
        client, des_path(model_id, "FactData"), params=params, max_rows=max_scan_rows
    )
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for r in raw:
        groups.setdefault(tuple(r.get(d) for d in dims), []).append(r)
    rows = []
    for key, members in groups.items():
        row = dict(zip(dims, key, strict=True))
        row.update({s["alias"]: _apply(s["op"], [m.get(s["column"]) for m in members]) for s in specs})
        rows.append(row)
    _sort(rows, order)
    env = page_envelope(rows[:top], has_more=len(rows) > top)
    env.update(aggregation="client", rows_scanned=len(raw), scan_truncated=truncated)
    if truncated:
        env["note"] = (
            f"Only the first {len(raw)} fact rows were scanned, so results are partial — "
            "add a filter or raise max_scan_rows. Only 'sum' is aggregated by SAC itself."
        )
    return env


def register(server: FastMCP, client: SACClient) -> None:
    read = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @server.tool(annotations=read)
    @safe
    async def read_aggregated_data(
        model_id: str,
        group_by: list[str],
        aggregates: list[dict[str, Any]],
        filter: str | None = None,
        orderby: list[str] | None = None,
        top: int = 200,
        max_scan_rows: int = DEFAULT_MAX_SCAN_ROWS,
    ) -> dict[str, Any]:
        """Group a model's facts by dimensions and aggregate measures.

        ``sum`` is computed by SAC (``FactDataAggregation``) and is fast on any
        volume. ``average``, ``min``, ``max``, ``count`` and ``countdistinct``
        are computed by this server over at most ``max_scan_rows`` fact rows —
        check ``aggregation`` and ``scan_truncated`` in the result.

        Args:
            model_id: The model (provider) ID.
            group_by: Dimension names, e.g. ``["Entity"]``; ``[]`` for a grand total.
            aggregates: Specs like ``{"column": "LC_AMOUNT", "op": "sum", "alias": "Total"}``.
            filter: OData ``$filter`` applied first, e.g. ``"Version eq 'public.Actual'"``.
                On account-based models filter to one ``Account`` before summing.
            orderby: Sort by alias or dimension, e.g. ``["Total desc"]``.
            top: Maximum groups to return (default 200).
            max_scan_rows: Row budget for client-side operators (default 50000).
        """

        return await aggregate(
            client, model_id, group_by, aggregates,
            filter=filter, orderby=orderby, top=top, max_scan_rows=max_scan_rows,
        )

    @server.tool(annotations=read)
    @safe
    async def top_n_by_measure(
        model_id: str,
        dimension: str,
        measure: str,
        agg: Literal["sum", "average", "min", "max", "count"] = "sum",
        direction: Literal["desc", "asc"] = "desc",
        top: int = 10,
        filter: str | None = None,
    ) -> dict[str, Any]:
        """Rank a dimension's members by an aggregated measure (top or bottom N).

        Example: top 10 entities by ``LC_AMOUNT`` for actuals —
        ``dimension="Entity", measure="LC_AMOUNT", filter="Version eq 'public.Actual'"``.
        """

        alias = f"{agg.capitalize()}{measure}"
        return await aggregate(
            client, model_id, [dimension],
            [{"column": measure, "op": agg, "alias": alias}],
            filter=filter, orderby=[f"{alias} {direction}"], top=top,
        )

    @server.tool(annotations=read)
    @safe
    async def aggregate_by_dimension(
        model_id: str,
        dimension: str,
        measures: list[str],
        agg: Literal["sum", "average", "min", "max", "count", "countdistinct"] = "sum",
        filter: str | None = None,
        top: int = 200,
    ) -> dict[str, Any]:
        """Aggregate several measures grouped by one dimension (summary table)."""

        specs = [{"column": m, "op": agg, "alias": f"{agg.capitalize()}{m}"} for m in measures]
        return await aggregate(client, model_id, [dimension], specs, filter=filter, top=top)
