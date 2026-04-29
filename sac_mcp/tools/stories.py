"""Story discovery tools (``/api/v1/stories``)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import compact, page_envelope, safe


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_stories(
        include_models: bool = False,
        max_rows: int = 100,
    ) -> dict[str, Any]:
        """List stories visible to the OAuth client.

        Args:
            include_models: When true, includes the models referenced by each story
                in the response (uses ``?include=models``).
            max_rows: Cap the number of stories returned.
        """

        params: dict[str, Any] = {}
        if include_models:
            params["include"] = "models"
        rows: list[dict[str, Any]] = []
        async for r in client.paginate("/api/v1/stories", params=params, max_rows=max_rows):
            rows.append(r)
        return page_envelope(compact(rows))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_story(story_id: str) -> dict[str, Any]:
        """Return a single story by ID, including referenced models."""

        return await client.get_json(
            f"/api/v1/stories/{story_id}", params={"include": "models"}
        )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def search_stories(query: str, max_rows: int = 50) -> dict[str, Any]:
        """Case-insensitive substring match against story name / description."""

        q = query.lower()
        matched: list[dict[str, Any]] = []
        async for r in client.paginate("/api/v1/stories", max_rows=10_000):
            name = (r.get("name") or "").lower()
            desc = (r.get("description") or "").lower()
            if q in name or q in desc:
                matched.append(r)
                if len(matched) >= max_rows:
                    break
        return page_envelope(compact(matched))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_story_models(story_id: str) -> dict[str, Any]:
        """Return the list of models referenced by a story."""

        story = await client.get_json(
            f"/api/v1/stories/{story_id}", params={"include": "models"}
        )
        models = story.get("models") if isinstance(story, dict) else None
        return {"story_id": story_id, "models": models or []}
