"""Data Export Service tools — read fact, master and audit data via OData v4."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.odata import ODataQuery
from sac_mcp.tools._common import as_csv, compact, page_envelope, safe


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def read_fact_data(
        model_id: str,
        filter: str | None = None,
        select: list[str] | None = None,
        orderby: list[str] | None = None,
        top: int = 100,
        skip: int | None = None,
    ) -> dict[str, Any]:
        """Read fact data from a model via the OData Data Export Service.

        Args:
            model_id: The model (provider) ID.
            filter: Raw OData ``$filter`` expression, e.g. ``Year eq '2025'``.
            select: Project to a subset of columns.
            orderby: Sort columns (use ``"col desc"`` for descending).
            top: Page size; the tool may follow ``@odata.nextLink`` until
                ``top`` rows have been returned.
            skip: Skip the first N rows server-side.
        """

        q = ODataQuery(
            filter=filter, select=select or [], orderby=orderby or [], top=top, skip=skip
        )
        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            f"/api/v1/dataexport/providers/sac/{model_id}/Data",
            params=q.to_params(),
            max_rows=top,
        ):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def read_fact_data_delta(
        model_id: str, delta_token: str, top: int = 1000
    ) -> dict[str, Any]:
        """Continue an incremental (delta) fact-data read using a previously
        returned delta token. SAC supports delta extracts since Q4 2022."""

        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            f"/api/v1/dataexport/providers/sac/{model_id}/Data",
            params={"$deltatoken": delta_token, "$top": str(top)},
            max_rows=top,
        ):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def export_fact_data_csv(
        model_id: str,
        filter: str | None = None,
        select: list[str] | None = None,
        orderby: list[str] | None = None,
        max_rows: int = 5000,
    ) -> dict[str, Any]:
        """Read fact data and return it as a single CSV string (good for tables
        too large to fit comfortably in a JSON response)."""

        q = ODataQuery(
            filter=filter, select=select or [], orderby=orderby or [], top=min(max_rows, 1000)
        )
        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            f"/api/v1/dataexport/providers/sac/{model_id}/Data",
            params=q.to_params(),
            max_rows=max_rows,
        ):
            rows.append(r)
        return {"row_count": len(rows), "csv": as_csv(rows)}

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def read_master_data(
        model_id: str,
        dimension: str | None = None,
        filter: str | None = None,
        top: int = 200,
    ) -> dict[str, Any]:
        """Read master / dimension member data for a model.

        If ``dimension`` is given, hits the dimension-specific endpoint;
        otherwise reads the top-level MasterData entity set.
        """

        path = f"/api/v1/dataexport/providers/sac/{model_id}/MasterData"
        if dimension:
            path = f"/api/v1/dataexport/providers/sac/{model_id}/{dimension}MasterData"
        q = ODataQuery(filter=filter, top=top)
        rows: list[dict[str, Any]] = []
        async for r in client.paginate(path, params=q.to_params(), max_rows=top):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_dimension_members(
        model_id: str, dimension: str, top: int = 200
    ) -> dict[str, Any]:
        """Convenience: list members of one dimension for a model."""

        return await read_master_data.__wrapped__(  # type: ignore[attr-defined]
            model_id=model_id, dimension=dimension, top=top
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def read_audit_data(
        model_id: str,
        filter: str | None = None,
        top: int = 200,
    ) -> dict[str, Any]:
        """Read the audit log entries associated with a model's data changes."""

        q = ODataQuery(filter=filter, top=top)
        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            f"/api/v1/dataexport/providers/sac/{model_id}/AuditData",
            params=q.to_params(),
            max_rows=top,
        ):
            rows.append(r)
        return page_envelope(compact(rows))
