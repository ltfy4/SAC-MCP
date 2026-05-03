"""Public-dimension tools.

Public dimensions are tenant-wide shared dimensions (cost centres, org
hierarchies, products) reused across multiple models. They live under a
separate OData namespace from private model dimensions:
``/api/v1/dataexport/providers/sac_public_dimensions``.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import compact, page_envelope, safe

_NAMESPACE = "sac_public_dimensions"
_BASE = f"/api/v1/dataexport/providers/{_NAMESPACE}"


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_public_dimensions(top: int = 100) -> dict[str, Any]:
        """List all public dimensions available on the tenant."""

        rows: list[dict[str, Any]] = []
        async for r in client.paginate(_BASE, params={"$top": top}, max_rows=top):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def read_public_dimension_master_data(
        dimension_id: str,
        top: int = 200,
        skip: int = 0,
        filter: str | None = None,
        select: str | None = None,
        orderby: str | None = None,
    ) -> dict[str, Any]:
        """Read master data members for a specific public dimension.

        Args:
            dimension_id: The public-dimension ID (e.g. ``SAP_ALL_PRODUCT``).
            top: Page size cap (default 200).
            skip: Server-side row skip.
            filter: Raw OData ``$filter`` expression.
            select: Comma-separated ``$select`` projection.
            orderby: Raw ``$orderby`` clause.
        """

        params: dict[str, Any] = {"$top": top, "$skip": skip}
        if filter:
            params["$filter"] = filter
        if select:
            params["$select"] = select
        if orderby:
            params["$orderby"] = orderby

        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            f"{_BASE}/{dimension_id}/MasterData", params=params, max_rows=top
        ):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def read_public_dimension_hierarchies(
        dimension_id: str,
        top: int = 200,
        filter: str | None = None,
    ) -> dict[str, Any]:
        """Read master data with hierarchy nodes for a public dimension."""

        params: dict[str, Any] = {"$top": top}
        if filter:
            params["$filter"] = filter

        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            f"{_BASE}/{dimension_id}/MasterDataWithHierarchies",
            params=params,
            max_rows=top,
        ):
            rows.append(r)
        return page_envelope(compact(rows))
