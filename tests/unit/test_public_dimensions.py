"""Tests for public dimension tools on the Data Import API."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import public_dimensions

TENANT = "https://tenant.example.com"
ROOT = f"{TENANT}/api/v1/dataimport/publicDimensions"


def _register(client: SACClient) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    public_dimensions.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


@pytest.mark.asyncio
async def test_list_public_dimensions(client: SACClient, respx_mock: respx.MockRouter) -> None:
    respx_mock.get(ROOT).mock(return_value=httpx.Response(200, json={"value": [{"id": "CC"}]}))
    result = await _register(client)["list_public_dimensions"]()
    assert result["rows"] == [{"id": "CC"}]


@pytest.mark.asyncio
async def test_get_public_dimension_encodes_id(client: SACClient, respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{ROOT}/a%2Fb").mock(return_value=httpx.Response(200, json={"id": "a/b"}))
    respx_mock.get(f"{ROOT}/a%2Fb/metadata").mock(return_value=httpx.Response(200, json={}))
    result = await _register(client)["get_public_dimension"](dimension_id="a/b")
    assert result["dimension"] == {"id": "a/b"}
