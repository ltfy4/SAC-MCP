"""Server-side aggregation tools via the SAC Data Export OData Aggregation entity."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import compact, page_envelope, safe

_VALID_OPS = frozenset({"sum", "average", "min", "max", "countdistinct", "count"})


def _build_apply(group_by: list[str], aggregates: list[dict[str, Any]]) -> str:
    """Build an OData $apply groupby((...), aggregate(...)) expression.

    aggregates = [{"column": "Amount", "op": "sum", "alias": "TotalAmount"}, ...]
    Returns: groupby((Region,Year),aggregate(Amount with sum as TotalAmount,...))
    """
    for agg in aggregates:
        op = str(agg.get("op", "")).lower()
        if op not in _VALID_OPS:
            raise ValueError(
                f"Invalid aggregation operator {op!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_OPS))}"
            )

    agg_parts = ", ".join(
        f"{agg['column']} with {str(agg['op']).lower()} as {agg['alias']}"
        for agg in aggregates
    )

    if group_by:
        dims = ",".join(group_by)
        return f"groupby(({dims}),aggregate({agg_parts}))"
    return f"aggregate({agg_parts})"


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def read_aggregated_data(
        model_id: str,
        group_by: list[str],
        aggregates: list[dict[str, Any]],
        filter: str | None = None,
        orderby: list[str] | None = None,
        top: int = 200,
    ) -> dict[str, Any]:
        """Read server-side aggregated data from a SAC model via the OData Aggregation entity.

        Performs GROUP BY + measure aggregation entirely in the SAC tenant — no
        client-side aggregation needed. Use this whenever you need sums, averages,
        counts, or rankings across dimension members.

        Args:
            model_id: The SAC model (provider) ID.
            group_by: Dimension column names to group by, e.g. ``["Region", "Year"]``.
                Pass an empty list to aggregate across all rows.
            aggregates: List of aggregation specs, each a dict with keys:
                - ``column``: the measure or column name (e.g. ``"Amount"``).
                - ``op``: one of ``sum``, ``average``, ``min``, ``max``,
                  ``countdistinct``, ``count``.
                - ``alias``: output column name (e.g. ``"TotalAmount"``).
            filter: Optional OData ``$filter`` expression applied before aggregation.
            orderby: Optional sort columns, e.g. ``["TotalAmount desc"]``.
            top: Maximum rows to return (default 200).
        """
        apply = _build_apply(group_by, aggregates)
        params: dict[str, Any] = {"$apply": apply, "$top": str(top)}
        if filter:
            params["$filter"] = filter
        if orderby:
            params["$orderby"] = ",".join(orderby)

        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            f"/api/v1/dataexport/providers/sac/{model_id}/Aggregation",
            params=params,
            max_rows=top,
        ):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
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
        """Return the top (or bottom) N dimension members ranked by an aggregated measure.

        Convenience wrapper around the Aggregation entity for ranking queries such
        as "top 10 regions by total sales" or "bottom 5 products by average margin".

        Args:
            model_id: The SAC model (provider) ID.
            dimension: Dimension column to group by, e.g. ``"Region"``.
            measure: Measure column to aggregate, e.g. ``"Amount"``.
            agg: Aggregation function: ``sum``, ``average``, ``min``, ``max``,
                or ``count``.
            direction: ``desc`` for top N (highest first), ``asc`` for bottom N.
            top: Number of members to return (default 10).
            filter: Optional OData ``$filter`` expression applied before aggregation.
        """
        alias = f"{agg.capitalize()}{measure}"
        apply = _build_apply(
            [dimension], [{"column": measure, "op": agg, "alias": alias}]
        )
        params: dict[str, Any] = {
            "$apply": apply,
            "$orderby": f"{alias} {direction}",
            "$top": str(top),
        }
        if filter:
            params["$filter"] = filter

        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            f"/api/v1/dataexport/providers/sac/{model_id}/Aggregation",
            params=params,
            max_rows=top,
        ):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def aggregate_by_dimension(
        model_id: str,
        dimension: str,
        measures: list[str],
        agg: str = "sum",
        filter: str | None = None,
        top: int = 200,
    ) -> dict[str, Any]:
        """Aggregate multiple measures grouped by a single dimension.

        Groups all rows by one dimension and applies the same aggregation function
        to each requested measure. Useful for summary tables like "sales by region"
        or "headcount by department across all cost types".

        Args:
            model_id: The SAC model (provider) ID.
            dimension: Dimension column to group by, e.g. ``"Region"``.
            measures: Measure column names to aggregate, e.g. ``["Amount", "Quantity"]``.
            agg: Aggregation function (``sum``, ``average``, ``min``, ``max``,
                ``countdistinct``, ``count``). Applied to every measure.
            filter: Optional OData ``$filter`` expression applied before aggregation.
            top: Maximum rows to return (default 200).
        """
        agg_specs = [
            {"column": m, "op": agg, "alias": f"{agg.capitalize()}{m}"}
            for m in measures
        ]
        apply = _build_apply([dimension], agg_specs)
        params: dict[str, Any] = {"$apply": apply, "$top": str(top)}
        if filter:
            params["$filter"] = filter

        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            f"/api/v1/dataexport/providers/sac/{model_id}/Aggregation",
            params=params,
            max_rows=top,
        ):
            rows.append(r)
        return page_envelope(compact(rows))
