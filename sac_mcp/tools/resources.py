"""File-repository / resources tools (``/api/v1/filerepository/Resources``).

Lets the LLM browse folders, stories, insights, models and applications via the
shared OData ``Resources`` endpoint.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.odata import ODataQuery, and_, contains, eq
from sac_mcp.tools._common import compact, page_envelope, safe

ResourceType = Literal[
    "FOLDER", "STORY", "MODEL", "APPLICATION", "DATASET", "BOOKLET", "FILE", "OTHER"
]


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_resources(
        resource_type: ResourceType | None = None,
        name_contains: str | None = None,
        parent_id: str | None = None,
        max_rows: int = 200,
    ) -> dict[str, Any]:
        """List entries from the SAC file repository.

        Optionally filter by type (FOLDER/STORY/MODEL/APPLICATION/...), name
        substring, or parent folder ID.
        """

        clauses = []
        if resource_type is not None:
            clauses.append(eq("resourceType", resource_type))
        if name_contains:
            clauses.append(contains("name", name_contains))
        if parent_id:
            clauses.append(eq("parentId", parent_id))

        q = ODataQuery(filter=and_(*clauses) or None, top=min(max_rows, 1000))
        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            "/api/v1/filerepository/Resources", params=q.to_params(), max_rows=max_rows
        ):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_resource(resource_id: str) -> dict[str, Any]:
        """Fetch a single repository resource by ID."""

        return await client.get_json(
            f"/api/v1/filerepository/Resources('{resource_id}')"
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_folders(parent_id: str | None = None, max_rows: int = 200) -> dict[str, Any]:
        """Convenience: list folders under ``parent_id`` (or top-level if omitted)."""

        return await list_resources.__wrapped__(  # type: ignore[attr-defined]
            resource_type="FOLDER", parent_id=parent_id, max_rows=max_rows
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def find_by_type(resource_type: ResourceType, max_rows: int = 200) -> dict[str, Any]:
        """Convenience: list every resource of a given type."""

        return await list_resources.__wrapped__(  # type: ignore[attr-defined]
            resource_type=resource_type, max_rows=max_rows
        )
