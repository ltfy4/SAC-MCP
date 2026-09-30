"""Calendar tools (``/api/v1/calendar/events``).

Verified live: ``GET /api/v1/calendar/events`` answers 405 — SAC has no
endpoint that lists calendar events, so there is no list tool. Single events
are read and updated by ID; task comments have no public endpoint.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.paths import seg
from sac_mcp.tools._common import safe

TaskStatus = Literal["Open", "InProgress", "Completed", "Cancelled"]


def register(server: FastMCP, client: SACClient) -> None:
    read = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @server.tool(annotations=read)
    @safe
    async def get_calendar_task(task_id: str) -> dict[str, Any]:
        """Return one calendar event (task or process) by its event ID."""

        return await client.get_json(f"/api/v1/calendar/events/{seg(task_id)}")

    @server.tool(annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True))
    @safe
    async def update_task_status(task_id: str, status: TaskStatus) -> dict[str, Any]:
        """Set the status of a calendar event. **Mutates the tenant.**

        Sends ``PATCH /api/v1/calendar/events/{id}``; SAC rejects the change
        with 400 if the event type does not allow that status.
        """

        result = await client.patch_json(
            f"/api/v1/calendar/events/{seg(task_id)}", json={"status": status}
        )
        return result if isinstance(result, dict) else {"ok": True}
