"""Tests for Data Action tools (listed from the file repository)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import dataactions

TENANT = "https://tenant.example.com"
REPO_PATH = f"{TENANT}/api/v1/filerepository/Resources"


def _register(client: SACClient) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    dataactions.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


@pytest.mark.asyncio
async def test_list_data_actions_filters_repository_by_type(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": [{"resourceId": "DA1", "name": "Copy Plan"}]})

    respx_mock.get(REPO_PATH).mock(side_effect=handler)
    result = await _register(client)["list_data_actions"](max_rows=10)

    assert result["rows"] == [{"resourceId": "DA1", "name": "Copy Plan"}]
    assert captured["params"]["$filter"] == "resourceType eq 'DATAACTION'"
    assert captured["params"]["$top"] == "11"


@pytest.mark.asyncio
async def test_get_data_action_not_found(client: SACClient, respx_mock: respx.MockRouter) -> None:
    respx_mock.get(REPO_PATH).mock(return_value=httpx.Response(200, json={"value": []}))
    result = await _register(client)["get_data_action"](data_action_id="nope")
    assert result["code"] == "not_found"
