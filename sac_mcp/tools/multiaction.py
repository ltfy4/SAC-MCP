"""Multi-Action tools — list and trigger SAC Multi-Actions."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import safe


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_multi_actions(top: int = 100) -> dict[str, Any]:
        """List Multi-Actions defined in the tenant."""

        return await client.get_json(
            "/api/v1/multiaction/multiactions", params={"$top": top}
        )

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def run_multi_action(
        multi_action_id: str, parameters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Trigger a Multi-Action. Returns a run/job ID."""

        body: dict[str, Any] = {}
        if parameters:
            body["parameters"] = parameters
        return await client.post_json(
            f"/api/v1/multiaction/multiactions/{multi_action_id}/runs", json=body
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_multi_action_run_status(run_id: str) -> dict[str, Any]:
        """Return the status of a Multi-Action run."""

        return await client.get_json(f"/api/v1/multiaction/runs/{run_id}")
