"""Public dimension tools (SAP Data Import API).

The Data Export namespace ``sac_public_dimensions`` does not exist (404).
Public dimensions are listed and described through
``/api/v1/dataimport/publicDimensions``; their members are read through any
model that uses them (``list_dimension_members``). Requires Data Import access
for the OAuth client (otherwise error 3401).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.paths import DATA_IMPORT_ROOT, seg
from sac_mcp.tools._common import collect, page_envelope, safe

_ROOT = f"{DATA_IMPORT_ROOT}/publicDimensions"


def register(server: FastMCP, client: SACClient) -> None:
    read = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @server.tool(annotations=read)
    @safe
    async def list_public_dimensions(top: int = 100) -> dict[str, Any]:
        """List the public (shared) dimensions on the tenant."""

        rows, more = await collect(client, _ROOT, max_rows=top)
        return page_envelope(rows, has_more=more)

    @server.tool(annotations=read)
    @safe
    async def get_public_dimension(dimension_id: str) -> dict[str, Any]:
        """Describe one public dimension and the columns its member import expects.

        To read its members, call ``list_dimension_members`` on a model that uses it.
        """

        base = f"{_ROOT}/{seg(dimension_id)}"
        return {
            "dimension": await client.get_json(base),
            "metadata": await client.get_json(f"{base}/metadata"),
        }
