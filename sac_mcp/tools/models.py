"""Model catalogue tools (Data Export Administration namespace)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.odata import ODataQuery, contains
from sac_mcp.tools._common import compact, page_envelope, safe

_ADMIN = "/api/v1/dataexport/administration/Namespaces('sac')/Providers"


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_models(name_contains: str | None = None, max_rows: int = 200) -> dict[str, Any]:
        """List all models (a.k.a. providers) on the SAC tenant.

        Optionally filter by name substring (server-side ``$filter``).
        """

        q = ODataQuery(
            filter=contains("Name", name_contains) if name_contains else None,
            top=min(max_rows, 1000),
        )
        rows: list[dict[str, Any]] = []
        async for r in client.paginate(_ADMIN, params=q.to_params(), max_rows=max_rows):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_model_metadata(model_id: str) -> dict[str, Any]:
        """Return the OData ``$metadata`` document for a model (dimensions, measures, types)."""

        # Provider-level $metadata describes the EntitySet for one model.
        return await client.get_json(
            f"/api/v1/dataexport/providers/sac/{model_id}/$metadata"
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_dimensions(model_id: str) -> dict[str, Any]:
        """List the dimension attributes available for a model."""

        meta = await client.get_json(f"/api/v1/dataexport/providers/sac/{model_id}/$metadata")
        # SAC also exposes a friendly Properties endpoint when available.
        try:
            props = await client.get_json(
                f"/api/v1/dataexport/providers/sac/{model_id}/Properties"
            )
        except Exception:
            props = None
        return {"model_id": model_id, "metadata": meta, "properties": props}

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_measures(model_id: str) -> dict[str, Any]:
        """List the measures (account members) for a model."""

        try:
            measures = await client.get_json(
                f"/api/v1/dataexport/providers/sac/{model_id}/Measures"
            )
            return {"model_id": model_id, "measures": measures}
        except Exception:
            # Fallback: project measures from $metadata.
            meta = await client.get_json(
                f"/api/v1/dataexport/providers/sac/{model_id}/$metadata"
            )
            return {"model_id": model_id, "metadata": meta}
