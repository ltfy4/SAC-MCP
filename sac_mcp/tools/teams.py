"""SCIM teams (groups) tools (``/api/v1/scim/Groups``)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import safe


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_teams(
        filter: str | None = None, start_index: int = 1, count: int = 100
    ) -> dict[str, Any]:
        """List SCIM groups (teams)."""

        params: dict[str, Any] = {"startIndex": start_index, "count": count}
        if filter:
            params["filter"] = filter
        return await client.get_json("/api/v1/scim/Groups", params=params)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_team(team_id: str) -> dict[str, Any]:
        """Return one team / group by ID."""

        return await client.get_json(f"/api/v1/scim/Groups/{team_id}")

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def add_member(team_id: str, user_id: str) -> dict[str, Any]:
        """Add a user to a team."""

        body = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "add", "path": "members", "value": [{"value": user_id}]}
            ],
        }
        return await client.patch_json(f"/api/v1/scim/Groups/{team_id}", json=body)

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def remove_member(team_id: str, user_id: str) -> dict[str, Any]:
        """Remove a user from a team."""

        body = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {
                    "op": "remove",
                    "path": f'members[value eq "{user_id}"]',
                }
            ],
        }
        return await client.patch_json(f"/api/v1/scim/Groups/{team_id}", json=body)
