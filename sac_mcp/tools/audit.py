"""Activity (audit) log tools (``/api/v1/audit/activities/exportActivities``).

``/api/v1/auditing/AuditLog`` does not exist (404). The activity export does
(verified: it answers 406 to ``Accept: application/json``), so it is read
with a content-type-aware reader. Column names are whatever SAC exports;
``recent_changes_for_user`` therefore matches columns by name pattern.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.odata import ODataQuery
from sac_mcp.tools._common import read_rows_any, safe

_EXPORT = "/api/v1/audit/activities/exportActivities"


def register(server: FastMCP, client: SACClient) -> None:
    read = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @server.tool(annotations=read)
    @safe
    async def query_audit_log(
        filter: str | None = None,
        top: int = 200,
        orderby: list[str] | None = None,
    ) -> dict[str, Any]:
        """Export activity-log entries (who did what, when).

        Args:
            filter: Optional OData ``$filter`` passed to SAC's export.
            top: Maximum entries to return (default 200).
            orderby: Optional sort, e.g. ``["Timestamp desc"]``.
        """

        q = ODataQuery(filter=filter, orderby=orderby or [], top=top)
        return await read_rows_any(client, _EXPORT, params=q.to_params(), max_rows=top)

    @server.tool(annotations=read)
    @safe
    async def recent_changes_for_user(username: str, since_iso: str, top: int = 100) -> dict[str, Any]:
        """Activity-log entries for one user since an ISO timestamp.

        Filters the export client-side: a row matches when a column whose
        name contains "user" equals ``username`` (case-insensitive) and a
        column containing "time"/"date" is at or after ``since_iso``.
        """

        exported = await read_rows_any(client, _EXPORT, max_rows=20_000)
        rows = exported.get("rows")
        if rows is None:
            return exported
        wanted = username.lower()

        def matches(row: dict[str, Any]) -> bool:
            users = [str(v).lower() for k, v in row.items() if "user" in k.lower()]
            times = [str(v) for k, v in row.items() if "time" in k.lower() or "date" in k.lower()]
            return wanted in users and any(t >= since_iso for t in times)

        hits = [r for r in rows if matches(r)]
        return {"content_type": exported.get("content_type"), "rows": hits[:top],
                "row_count": min(len(hits), top), "has_more": len(hits) > top}
