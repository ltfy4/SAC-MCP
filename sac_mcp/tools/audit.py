"""Tenant-wide audit tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.odata import ODataQuery, and_, eq, gt
from sac_mcp.tools._common import compact, page_envelope, safe


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def query_audit_log(
        filter: str | None = None,
        top: int = 200,
        orderby: list[str] | None = None,
    ) -> dict[str, Any]:
        """Query the SAC audit log via OData (raw filter passthrough).

        Common columns include ``Action``, ``UserName``, ``Timestamp``,
        ``EntityType``, ``EntityId``.
        """

        q = ODataQuery(filter=filter, top=top, orderby=orderby or ["Timestamp desc"])
        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            "/api/v1/auditing/AuditLog", params=q.to_params(), max_rows=top
        ):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def recent_changes_for_user(
        username: str, since_iso: str, top: int = 100
    ) -> dict[str, Any]:
        """Return audit-log entries for a given user since a given ISO timestamp."""

        q = ODataQuery(
            filter=and_(eq("UserName", username), gt("Timestamp", since_iso)),
            top=top,
            orderby=["Timestamp desc"],
        )
        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            "/api/v1/auditing/AuditLog", params=q.to_params(), max_rows=top
        ):
            rows.append(r)
        return page_envelope(compact(rows))
