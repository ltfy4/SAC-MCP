"""MCP tools for SAP Analytics Cloud Widget Query API.

Allows programmatic access to widget data from SAC stories. The Widget Query
API returns data the way a story renders it (aggregated, formatted), as opposed
to the OData Data Export API which returns raw rows.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import safe


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_widget_data(
        story_id: str,
        widget_id: str,
        type: Literal["kpiTile"] = "kpiTile",
    ) -> dict[str, Any]:
        """Fetch data from a specific widget in a SAC story.

        Currently only supports ``kpiTile`` (numeric chart) widgets — other
        widget types return an error from SAC.

        Args:
            story_id: The SAC story ID containing the widget.
            widget_id: The widget technical name (e.g. ``Chart_1``).
            type: Widget type. Only ``kpiTile`` is currently supported.
        """

        result = await client.get_json(
            "/widgetquery/getWidgetData",
            params={"storyId": story_id, "widgetId": widget_id, "type": type},
        )
        if isinstance(result, dict):
            return result
        return {"data": result}

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_story_widgets(story_id: str) -> dict[str, Any]:
        """List widget metadata embedded in a SAC story (best effort).

        SAC's story endpoint may return widgets/charts under various keys
        (``widgets``, ``charts``, ``pages[].widgets``). This tool inspects the
        story payload and surfaces any widget descriptors it can find. If none
        are present, returns an empty list — does not fabricate data.
        """

        story = await client.get_json(
            f"/api/v1/stories/{story_id}", params={"include": "widgets,models"}
        )
        widgets: list[dict[str, Any]] = []
        if isinstance(story, dict):
            for key in ("widgets", "charts"):
                items = story.get(key)
                if isinstance(items, list):
                    widgets.extend(w for w in items if isinstance(w, dict))
            pages = story.get("pages")
            if isinstance(pages, list):
                for page in pages:
                    if isinstance(page, dict):
                        items = page.get("widgets") or page.get("charts")
                        if isinstance(items, list):
                            widgets.extend(w for w in items if isinstance(w, dict))
        return {"story_id": story_id, "widgets": widgets, "widget_count": len(widgets)}
