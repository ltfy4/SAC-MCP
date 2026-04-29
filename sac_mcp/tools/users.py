"""SCIM user management tools (``/api/v1/scim/Users``)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import safe


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_users(
        filter: str | None = None, start_index: int = 1, count: int = 100
    ) -> dict[str, Any]:
        """List SCIM users. Supports raw SCIM ``filter`` syntax.

        Example filter: ``userName eq "alice@example.com"`` or ``active eq true``.
        """

        params: dict[str, Any] = {"startIndex": start_index, "count": count}
        if filter:
            params["filter"] = filter
        return await client.get_json("/api/v1/scim/Users", params=params)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_user(user_id: str) -> dict[str, Any]:
        """Return one SCIM user by internal ID."""

        return await client.get_json(f"/api/v1/scim/Users/{user_id}")

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def create_user(
        user_name: str,
        display_name: str | None = None,
        email: str | None = None,
        active: bool = True,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new SCIM user."""

        body: dict[str, Any] = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": user_name,
            "active": active,
        }
        if display_name:
            body["displayName"] = display_name
        if email:
            body["emails"] = [{"value": email, "primary": True}]
        if extra:
            body.update(extra)
        return await client.post_json("/api/v1/scim/Users", json=body)

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def update_user(user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """PATCH a SCIM user. ``patch`` is a SCIM PatchOp body (``Operations`` list)."""

        if "schemas" not in patch:
            patch = {
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                **patch,
            }
        return await client.patch_json(f"/api/v1/scim/Users/{user_id}", json=patch)

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def deactivate_user(user_id: str) -> dict[str, Any]:
        """Mark a user inactive (preferred over delete to preserve audit trail)."""

        body = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "active", "value": False}],
        }
        return await client.patch_json(f"/api/v1/scim/Users/{user_id}", json=body)
