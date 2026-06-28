"""Model monitoring tools — data freshness, row counts, job history."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.odata import ODataQuery, gt
from sac_mcp.tools._common import compact, page_envelope, safe


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_monitored_models(
        top: int = 200,
        filter: str | None = None,
    ) -> dict[str, Any]:
        """List all models with their monitoring metadata.

        Key fields: size, rowCount, lastImportTime, lastModifiedBy, lastModifiedTime.

        Args:
            top: Maximum number of models to return (default 200).
            filter: Optional OData $filter expression to narrow results.
        """
        q = ODataQuery(filter=filter, top=top)
        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            "/api/v1/monitoring/models", params=q.to_params(), max_rows=top
        ):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_model_monitoring(model_id: str) -> dict[str, Any]:
        """Return monitoring detail for a single model.

        Includes size, rowCount, lastImportTime, lastModifiedBy, lastModifiedTime.

        Args:
            model_id: The SAC model ID.
        """
        return await client.get_json(f"/api/v1/monitoring/models/{model_id}")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_model_job_history(
        model_id: str,
        top: int = 50,
        since_iso: str | None = None,
    ) -> dict[str, Any]:
        """Return recent import/refresh jobs for a model.

        Args:
            model_id: The SAC model ID.
            top: Maximum number of job records to return (default 50).
            since_iso: ISO 8601 timestamp; only jobs started after this time are returned.
        """
        f = gt("startTime", since_iso) if since_iso else None
        q = ODataQuery(filter=f, top=top)
        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            f"/api/v1/monitoring/models/{model_id}/jobHistory",
            params=q.to_params(),
            max_rows=top,
        ):
            rows.append(r)
        return page_envelope(compact(rows))
