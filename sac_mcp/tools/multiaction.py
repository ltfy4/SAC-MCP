"""Multi-Action tools.

Verified live: SAC has no Multi-Action list endpoint (``GET
/api/v1/multiActions`` is 404); Multi-Actions are listed from the file
repository, where their resource type is ``PLANNINGSEQUENCE``. Execution
uses SAP's Multi-Action API: ``POST /api/v1/multiActions/{id}/executions``
with ``{"parameterValues": [...]}`` and status at
``.../executions/{executionId}``.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.paths import seg
from sac_mcp.tools._common import safe
from sac_mcp.tools.resources import list_repository


def register(server: FastMCP, client: SACClient) -> None:
    read = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @server.tool(annotations=read)
    @safe
    async def list_multi_actions(name_contains: str | None = None, max_rows: int = 100) -> dict[str, Any]:
        """List Multi-Actions (file-repository resources of type ``PLANNINGSEQUENCE``).

        Rows carry ``resourceId``, ``objectId``, ``name`` and ``description``.
        """

        return await list_repository(
            client, resource_type="PLANNINGSEQUENCE", name_contains=name_contains, max_rows=max_rows
        )

    @server.tool(annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True))
    @safe
    async def run_multi_action(
        multi_action_id: str,
        parameter_values: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Trigger a Multi-Action run. **This writes to planning models.**

        Args:
            multi_action_id: The Multi-Action ID in SAC's ``<package>:<id>``
                form, e.g. ``"t.TEST:CEEFOKMRUKJBY5BN47F1NS2L8G"`` (see
                ``objectId`` in ``list_multi_actions``).
            parameter_values: Values for the Multi-Action's parameters, e.g.
                ``[{"parameterId": "Version", "value": {"memberIds": ["public.Plan"]}}]``.
                Omit for Multi-Actions without parameters.

        Returns SAC's execution record; pass its ID to ``get_multi_action_run_status``.
        """

        result = await client.post_json(
            f"/api/v1/multiActions/{seg(multi_action_id)}/executions",
            json={"parameterValues": parameter_values or []},
        )
        return result if isinstance(result, dict) else {"result": result}

    @server.tool(annotations=read)
    @safe
    async def get_multi_action_run_status(multi_action_id: str, execution_id: str) -> dict[str, Any]:
        """Return the status of one Multi-Action execution."""

        return await client.get_json(
            f"/api/v1/multiActions/{seg(multi_action_id)}/executions/{seg(execution_id)}"
        )
