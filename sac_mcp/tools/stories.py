"""Story discovery tools (``/api/v1/stories``)."""

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
    async def list_stories(
        max_rows: int = 100,
        created_by: str | None = None,
        all_tenant_content: bool = False,
    ) -> dict[str, Any]:
        """List stories (from the file repository; ``/api/v1/stories`` ignores paging).

        Rows carry ``resourceId`` (use it as ``story_id``), ``name``,
        ``createdBy``, ``modifiedTime`` and ``openURL``. Use
        ``list_story_models`` for the models behind one story.

        Args:
            max_rows: Maximum stories (default 100).
            created_by: Only stories created by this user ID.
            all_tenant_content: Include private stories of all users (needs Manage).
        """

        return await list_repository(
            client,
            resource_type="STORY",
            created_by=created_by,
            all_tenant_content=all_tenant_content,
            max_rows=max_rows,
        )

    @server.tool(annotations=read)
    @safe
    async def get_story(story_id: str) -> dict[str, Any]:
        """Return a single story by ID, including referenced models."""

        return await client.get_json(
            f"/api/v1/stories/{seg(story_id)}", params={"include": "models"}
        )

    @server.tool(annotations=read)
    @safe
    async def search_stories(query: str, max_rows: int = 50) -> dict[str, Any]:
        """Find stories whose name or description contains ``query`` (case-insensitive)."""

        return await list_repository(
            client, resource_type="STORY", name_contains=query, max_rows=max_rows
        )

    @server.tool(annotations=read)
    @safe
    async def list_story_models(story_id: str) -> dict[str, Any]:
        """Return the list of models referenced by a story."""

        story = await client.get_json(
            f"/api/v1/stories/{seg(story_id)}", params={"include": "models"}
        )
        models = story.get("models") if isinstance(story, dict) else None
        return {"story_id": story_id, "models": models or []}
