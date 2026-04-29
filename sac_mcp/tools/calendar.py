"""Calendar / planning task tools."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import safe

TaskStatus = Literal["Open", "InProgress", "Completed", "Cancelled"]


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_calendar_tasks(
        assignee: str | None = None,
        status: TaskStatus | None = None,
        top: int = 100,
    ) -> dict[str, Any]:
        """List calendar tasks, optionally filtered by assignee or status."""

        params: dict[str, Any] = {"$top": top}
        clauses = []
        if assignee:
            clauses.append(f"AssigneeId eq '{assignee}'")
        if status:
            clauses.append(f"Status eq '{status}'")
        if clauses:
            params["$filter"] = " and ".join(clauses)
        return await client.get_json("/api/v1/calendar/tasks", params=params)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_calendar_task(task_id: str) -> dict[str, Any]:
        """Return one calendar task by ID."""

        return await client.get_json(f"/api/v1/calendar/tasks/{task_id}")

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def update_task_status(task_id: str, status: TaskStatus) -> dict[str, Any]:
        """Set the status of a calendar task."""

        return await client.patch_json(
            f"/api/v1/calendar/tasks/{task_id}", json={"status": status}
        )

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def add_task_comment(task_id: str, comment: str) -> dict[str, Any]:
        """Append a comment to a calendar task."""

        return await client.post_json(
            f"/api/v1/calendar/tasks/{task_id}/comments", json={"text": comment}
        )
