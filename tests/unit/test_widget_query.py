"""Tests for the widget-query tool surface."""

from __future__ import annotations

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import widget_query

TENANT = "https://tenant.example.com"


def _register(client: SACClient) -> dict[str, object]:
    captured: dict[str, object] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    widget_query.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


@pytest.mark.asyncio
async def test_get_widget_data(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": 42, "unit": "USD"})

    respx_mock.get(f"{TENANT}/widgetquery/getWidgetData").mock(side_effect=handler)

    tools = _register(client)
    result = await tools["get_widget_data"](  # type: ignore[operator]
        story_id="S1", widget_id="Chart_1"
    )
    assert result["value"] == 42
    assert captured["params"]["storyId"] == "S1"  # type: ignore[index]
    assert captured["params"]["widgetId"] == "Chart_1"  # type: ignore[index]
    assert captured["params"]["type"] == "kpiTile"  # type: ignore[index]
