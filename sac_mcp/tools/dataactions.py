"""Data Action tools — list, inspect and trigger SAC Data Actions.

Data Actions are the planning-model automation primitive in SAC (copy,
cross-model copy, allocation, advanced-formula steps). They are distinct from
Multi-Actions, which orchestrate *several* data actions plus publish/import
steps; use the ``multiaction`` tools for those.

Endpoint family::

    GET  /api/v1/dataactions                              → list
    GET  /api/v1/dataactions/{id}                         → detail (incl. parameters)
    POST /api/v1/dataactions/{id}/executions              → trigger a run
    GET  /api/v1/dataactions/{id}/executions              → recent runs
    GET  /api/v1/dataactions/executions/{executionId}     → run status

Executions are asynchronous: triggering returns an ``executionId`` that must be
polled via :func:`get_data_action_status` until it reaches a terminal state.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import compact, page_envelope, safe


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_data_actions(
        top: int = 100,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        """List Data Actions defined in the tenant.

        Args:
            top: Maximum number of data actions to return (default 100).
            model_id: Optional model ID; only data actions targeting this model
                are returned.
        """

        params: dict[str, Any] = {"$top": top}
        if model_id:
            params["modelId"] = model_id
        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            "/api/v1/dataactions", params=params, max_rows=top
        ):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_data_action(data_action_id: str) -> dict[str, Any]:
        """Return one Data Action's detail, including its parameter definitions.

        Call this before :func:`run_data_action` to discover which parameters
        (and member values) the data action expects.

        Args:
            data_action_id: The Data Action ID (from ``list_data_actions``).
        """

        return await client.get_json(f"/api/v1/dataactions/{data_action_id}")

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def run_data_action(
        data_action_id: str,
        parameter_values: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Trigger a Data Action execution. **Mutates the target model.**

        The execution is asynchronous — poll the returned ``executionId`` with
        :func:`get_data_action_status` until it reaches a terminal state.

        Args:
            data_action_id: The Data Action ID (from ``list_data_actions``).
            parameter_values: Values for the data action's parameters, e.g.
                ``[{"parameterId": "TargetVersion", "value": "public.Actual"}]``.
                Use :func:`get_data_action` to discover the expected parameters.
        """

        body: dict[str, Any] = {}
        if parameter_values:
            body["parameterValues"] = parameter_values
        return await client.post_json(
            f"/api/v1/dataactions/{data_action_id}/executions", json=body
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_data_action_executions(
        data_action_id: str, top: int = 50
    ) -> dict[str, Any]:
        """List recent executions of one Data Action (newest first).

        Args:
            data_action_id: The Data Action ID.
            top: Maximum number of executions to return (default 50).
        """

        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            f"/api/v1/dataactions/{data_action_id}/executions",
            params={"$top": top},
            max_rows=top,
        ):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_data_action_status(execution_id: str) -> dict[str, Any]:
        """Return the status of a Data Action execution.

        Args:
            execution_id: The execution ID returned by ``run_data_action``.
        """

        return await client.get_json(
            f"/api/v1/dataactions/executions/{execution_id}"
        )
