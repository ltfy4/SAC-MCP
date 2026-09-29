"""FP&A analysis tools — version comparison, trends, completeness checks.

These are composite conveniences for financial planning & reporting workflows.
They call the same Data Export endpoints as the ``dataexport`` and
``aggregation`` modules but answer the questions planners actually ask:

* "Which plan/actual/forecast versions exist on this model?"
* "Show budget vs actual variance by cost centre."
* "How has revenue trended month over month?"
* "Which cost centres haven't submitted plan data yet?"

Everything here is read-only; nothing mutates the tenant.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.odata import and_, quote_odata_string
from sac_mcp.client.paths import des_path
from sac_mcp.tools._common import collect, page_envelope, safe
from sac_mcp.tools.aggregation import aggregate


def _num(value: Any) -> float | None:
    """Coerce a SAC cell value (often a string) to float; None if impossible."""

    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _member_id(row: dict[str, Any], dimension: str) -> str | None:
    """Best-effort extraction of a member ID from a master-data row."""

    for key in ("ID", "Id", "id", dimension, f"{dimension}___ID", f"{dimension}ID"):
        value = row.get(key)
        if value is not None:
            return str(value)
    return None


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_versions(
        model_id: str,
        version_dimension: str = "Version",
        top: int = 100,
    ) -> dict[str, Any]:
        """List the planning versions (categories) of a model.

        Returns the members of the model's version dimension — typically
        ``public.Actual``, ``public.Plan``, ``public.Forecast`` plus any
        private versions visible to the OAuth client. Use the returned IDs in
        ``compare_versions`` or as ``$filter`` values in fact-data reads.

        Args:
            model_id: The SAC model (provider) ID.
            version_dimension: Name of the version/category dimension
                (default ``Version``).
            top: Maximum members to return (default 100).
        """

        rows, more = await collect(
            client, des_path(model_id, f"{version_dimension}Master"), max_rows=top
        )
        return page_envelope(rows, has_more=more)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def compare_versions(
        model_id: str,
        measure: str,
        group_by: list[str],
        version_a: str,
        version_b: str,
        version_dimension: str = "Version",
        agg: str = "sum",
        filter: str | None = None,
        top: int = 200,
    ) -> dict[str, Any]:
        """Compare one measure between two versions — the variance report.

        Runs one server-side aggregation per version, joins the results on the
        ``group_by`` dimensions, and computes ``variance`` (a - b) and
        ``variance_pct`` (relative to version_b) per row. The classic use is
        actual vs plan: ``version_a='public.Actual', version_b='public.Plan'``
        makes positive variances mean "over plan".

        Args:
            model_id: The SAC model (provider) ID.
            measure: Measure column to aggregate, e.g. ``"Amount"``.
            group_by: Dimensions to break the variance down by,
                e.g. ``["CostCenter"]``.
            version_a: First version member ID, e.g. ``"public.Actual"``.
            version_b: Baseline version member ID, e.g. ``"public.Plan"``.
            version_dimension: Name of the version dimension (default ``Version``).
            agg: Aggregation function (default ``sum``).
            filter: Optional extra OData ``$filter`` applied to both reads,
                e.g. ``"Date ge '202601' and Account eq 'REVENUE'"``. On
                account-based models always pin one account.
            top: Maximum members per version read (default 200).

        Returns:
            Rows shaped ``{<group_by dims>, "version_a", "version_b",
            "variance", "variance_pct"}`` sorted by absolute variance,
            largest first.
        """

        spec = [{"column": measure, "op": agg, "alias": "Value"}]

        async def one_version(version: str) -> dict[tuple[str, ...], dict[str, Any]]:
            version_filter = f"{version_dimension} eq {quote_odata_string(version)}"
            result = await aggregate(
                client, model_id, group_by, spec, filter=and_(version_filter, filter or ""), top=top
            )
            rows = result["rows"]
            return {
                tuple(str(r.get(d)) for d in group_by): r for r in rows
            }

        rows_a = await one_version(version_a)
        rows_b = await one_version(version_b)

        merged: list[dict[str, Any]] = []
        for key in sorted(set(rows_a) | set(rows_b)):
            a = _num(rows_a.get(key, {}).get("Value"))
            b = _num(rows_b.get(key, {}).get("Value"))
            variance = a - b if a is not None and b is not None else None
            variance_pct = None
            if variance is not None and b is not None and b != 0:
                variance_pct = round(variance / abs(b) * 100, 2)
            row: dict[str, Any] = dict(zip(group_by, key, strict=True))
            row.update(
                version_a=a, version_b=b, variance=variance, variance_pct=variance_pct
            )
            merged.append(row)

        merged.sort(
            key=lambda r: abs(r["variance"]) if r["variance"] is not None else -1,
            reverse=True,
        )
        env = page_envelope(merged)
        env["versions"] = {"version_a": version_a, "version_b": version_b}
        return env

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def measure_trend(
        model_id: str,
        measure: str,
        time_dimension: str = "Date",
        periods: int = 12,
        agg: str = "sum",
        filter: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate a measure over time and compute period-over-period change.

        Returns the last ``periods`` periods in chronological order, each with
        the aggregated value plus ``change`` and ``change_pct`` versus the
        previous period — the raw material for trend and run-rate commentary.

        Args:
            model_id: The SAC model (provider) ID.
            measure: Measure column to aggregate, e.g. ``"Amount"``.
            time_dimension: Time dimension column to group by (default ``Date``).
            periods: Number of most recent periods to return (default 12).
            agg: Aggregation function (default ``sum``).
            filter: Optional OData ``$filter``, e.g. to pin one version:
                ``"Version eq 'public.Actual'"``.
        """

        result = await aggregate(
            client,
            model_id,
            [time_dimension],
            [{"column": measure, "op": agg, "alias": "Value"}],
            filter=filter,
            orderby=[f"{time_dimension} desc"],
            top=periods,
        )
        rows = list(reversed(result["rows"]))  # chronological

        trend: list[dict[str, Any]] = []
        prev: float | None = None
        for r in rows:
            value = _num(r.get("Value"))
            change = value - prev if value is not None and prev is not None else None
            change_pct = None
            if change is not None and prev is not None and prev != 0:
                change_pct = round(change / abs(prev) * 100, 2)
            trend.append(
                {
                    "period": r.get(time_dimension),
                    "value": value,
                    "change": change,
                    "change_pct": change_pct,
                }
            )
            if value is not None:
                prev = value
        return page_envelope(trend)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def check_data_completeness(
        model_id: str,
        dimension: str,
        measure: str,
        filter: str | None = None,
        max_members: int = 1000,
    ) -> dict[str, Any]:
        """Report which dimension members have no fact data booked.

        Compares the dimension's master-data members against the members that
        actually appear in (optionally filtered) fact data. The classic close /
        planning-round check: "which cost centres haven't submitted their plan
        for 2026 yet?" — pass ``filter="Version eq 'public.Plan' and Year eq
        '2026'"``.

        Args:
            model_id: The SAC model (provider) ID.
            dimension: Dimension to check, e.g. ``"CostCenter"``.
            measure: Any measure column of the model (needed for the
                aggregation probe), e.g. ``"Amount"``.
            filter: Optional OData ``$filter`` narrowing what counts as
                "booked" (version, year, ...).
            max_members: Maximum dimension members to check (default 1000).
        """

        member_rows, _ = await collect(
            client, des_path(model_id, f"{dimension}Master"), max_rows=max_members
        )
        members = [m for m in (_member_id(r, dimension) for r in member_rows) if m is not None]

        # A group appears in FactDataAggregation only if it has booked data.
        booked_result = await aggregate(
            client,
            model_id,
            [dimension],
            [{"column": measure, "op": "sum", "alias": "N"}],
            filter=filter,
            top=max_members,
        )
        booked_rows = booked_result["rows"]
        booked = {str(r.get(dimension)) for r in booked_rows if r.get(dimension) is not None}

        missing = [m for m in members if m not in booked]
        return {
            "dimension": dimension,
            "total_members": len(members),
            "members_with_data": len(members) - len(missing),
            "missing_count": len(missing),
            "members_missing_data": missing,
            "filter": filter,
        }
