"""Tests for delta / difference tracking tools."""

from __future__ import annotations

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import difference

TENANT = "https://tenant.example.com"
MODEL_PATH = "/api/v1/dataexport/providers/sac/model1/Data"


def _register(client: SACClient) -> dict[str, object]:
    captured: dict[str, object] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    difference.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


@pytest.mark.asyncio
async def test_init_delta_tracking(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["prefer"] = request.headers.get("prefer")
        return httpx.Response(
            200,
            json={
                "value": [{"id": 1}],
                "@odata.deltaLink": (
                    f"{TENANT}{MODEL_PATH}?$deltatoken=TOKEN123"
                ),
            },
        )

    respx_mock.get(f"{TENANT}{MODEL_PATH}").mock(side_effect=handler)

    tools = _register(client)
    result = await tools["init_delta_tracking"](model_id="model1")  # type: ignore[operator]
    assert result["delta_token"] == "TOKEN123"
    assert result["row_count"] == 1
    assert captured["prefer"] == "odata.track-changes"


@pytest.mark.asyncio
async def test_get_delta_changes(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "value": [{"id": 2, "_op": "U"}],
                "@odata.deltaLink": f"{TENANT}{MODEL_PATH}?$deltatoken=TOKEN456",
            },
        )

    respx_mock.get(f"{TENANT}{MODEL_PATH}").mock(side_effect=handler)

    tools = _register(client)
    result = await tools["get_delta_changes"](  # type: ignore[operator]
        model_id="model1", delta_token="TOKEN123"
    )
    assert result["delta_token"] == "TOKEN456"
    assert result["row_count"] == 1
    assert captured["params"]["$deltatoken"] == "TOKEN123"  # type: ignore[index]


@pytest.mark.asyncio
async def test_init_delta_tracking_no_delta_link(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{TENANT}{MODEL_PATH}").mock(
        return_value=httpx.Response(200, json={"value": [{"id": 1}]})
    )
    tools = _register(client)
    result = await tools["init_delta_tracking"](model_id="model1")  # type: ignore[operator]
    assert result["delta_token"] == ""
    assert result["row_count"] == 1
