"""Model monitoring tools (``/api/v1/monitoring/{modelId}``).

Verified live: the monitoring endpoints exist but answer 406 to ``Accept:
application/json``, so the response is read by content type. SAP documents
only the per-model resource; the former list and job-history tools called
undocumented paths and are removed.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.paths import seg
from sac_mcp.tools._common import read_rows_any, safe


def register(server: FastMCP, client: SACClient) -> None:
    read = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @server.tool(annotations=read)
    @safe
    async def get_model_monitoring(model_id: str) -> dict[str, Any]:
        """Return monitoring information (size, row count, last changes) for one model."""

        return await read_rows_any(client, f"/api/v1/monitoring/{seg(model_id)}")
