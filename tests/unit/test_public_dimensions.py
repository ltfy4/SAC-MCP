"""Tests for the public-dimensions tool surface."""

from __future__ import annotations

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import public_dimensions
from sac_mcp.tools.public_dimensions import _BASE

TENANT = "https://tenant.example.com"


def _register(client: SACClient) -> dict[str, object]:
    captured: dict[str, object] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    public_dimensions.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


@pytest.mark.asyncio
async def test_list_public_dimensions(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{TENANT}{_BASE}").mock(
        return_value=httpx.Response(
            200, json={"value": [{"id": "SAP_ALL_PRODUCT", "description": "All Products"}]}
        )
    )
    tools = _register(client)
    result = await tools["list_public_dimensions"]()  # type: ignore[operator]
    assert result["row_count"] == 1
    assert result["rows"][0]["id"] == "SAP_ALL_PRODUCT"


@pytest.mark.asyncio
async def test_read_public_dimension_master_data(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{TENANT}{_BASE}/SAP_ALL_PRODUCT/MasterData").mock(
        return_value=httpx.Response(
            200, json={"value": [{"ID": "P1", "Name": "Widget"}]}
        )
    )
    tools = _register(client)
    result = await tools["read_public_dimension_master_data"](  # type: ignore[operator]
        dimension_id="SAP_ALL_PRODUCT", top=10, filter="ID eq 'P1'"
    )
    assert result["row_count"] == 1
    assert result["rows"][0]["ID"] == "P1"


@pytest.mark.asyncio
async def test_read_public_dimension_hierarchies(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(
        f"{TENANT}{_BASE}/SAP_ALL_PRODUCT/MasterDataWithHierarchies"
    ).mock(
        return_value=httpx.Response(
            200, json={"value": [{"ID": "P1", "Parent": "ROOT"}]}
        )
    )
    tools = _register(client)
    result = await tools["read_public_dimension_hierarchies"](  # type: ignore[operator]
        dimension_id="SAP_ALL_PRODUCT"
    )
    assert result["row_count"] == 1
    assert result["rows"][0]["Parent"] == "ROOT"
