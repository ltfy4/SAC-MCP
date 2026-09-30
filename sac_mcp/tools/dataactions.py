"""Data Action tools.

Verified live: ``/api/v1/dataactions`` does not exist (404) — SAC exposes no
REST API to trigger a Data Action directly. Data Actions are listed from the
file repository (resource type ``DATAACTION``) and executed by adding them
as a step of a Multi-Action and calling ``run_multi_action``.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.odata import eq
from sac_mcp.tools._common import safe
from sac_mcp.tools.resources import REPO, list_repository


def register(server: FastMCP, client: SACClient) -> None:
    read = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @server.tool(annotations=read)
    @safe
    async def list_data_actions(name_contains: str | None = None, max_rows: int = 100) -> dict[str, Any]:
        """List Data Actions (file-repository resources of type ``DATAACTION``).

        To execute one, run a Multi-Action that contains it (``run_multi_action``);
        SAC has no endpoint that triggers a Data Action on its own.
        """

        return await list_repository(
            client, resource_type="DATAACTION", name_contains=name_contains, max_rows=max_rows
        )

    @server.tool(annotations=read)
    @safe
    async def get_data_action(data_action_id: str) -> dict[str, Any]:
        """Return the repository entry (name, owner, timestamps) of one Data Action."""

        page = await client.get_json(
            REPO,
            params={"$filter": f"{eq('resourceId', data_action_id)} and resourceType eq 'DATAACTION'", "$top": 1},
        )
        rows = page.get("value", []) if isinstance(page, dict) else []
        if not rows:
            return {"error": f"No Data Action with id {data_action_id!r}", "code": "not_found"}
        return dict(rows[0])
