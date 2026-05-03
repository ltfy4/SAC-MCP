"""Tests for the plan-only NL→OData smart_query tool."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.client.odata import quote_odata_string
from sac_mcp.tools import smart_query

TENANT = "https://tenant.example.com"
MODEL = "Sales"
META_PATH = f"{TENANT}/api/v1/dataexport/providers/sac/{MODEL}/$metadata"
DATA_PATH = f"{TENANT}/api/v1/dataexport/providers/sac/{MODEL}/Data"

_METADATA_JSON = {
    "dimensions": [
        {"name": "Year"},
        {"name": "Quarter"},
        {"name": "Country"},
        {"name": "Product"},
    ],
    "measures": [
        {"name": "Revenue"},
        {"name": "Quantity"},
    ],
}

_MALFORMED_METADATA = "<not-actually-xml<<>"


def _register(client: SACClient) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    smart_query.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


@pytest.mark.asyncio
async def test_year_mention_produces_year_filter(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(META_PATH).mock(
        return_value=httpx.Response(200, json=_METADATA_JSON)
    )
    data_route = respx_mock.get(DATA_PATH)

    tools = _register(client)
    plan = await tools["smart_query"](
        model_id=MODEL, question="show me 2025 sales"
    )

    assert plan["suggested_filter"] == "Year eq '2025'"
    assert plan["next_call"]["filter"] == "Year eq '2025'"
    assert plan["model_id"] == MODEL
    assert "string literal" in plan["rationale"]
    # Plan-only: the tool must never have hit the data endpoint.
    assert not data_route.called


@pytest.mark.asyncio
async def test_top_n_by_revenue_sets_orderby_and_top(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(META_PATH).mock(
        return_value=httpx.Response(200, json=_METADATA_JSON)
    )
    data_route = respx_mock.get(DATA_PATH)

    tools = _register(client)
    plan = await tools["smart_query"](
        model_id=MODEL, question="top 5 by Revenue"
    )

    assert "Revenue desc" in plan["suggested_orderby"]
    assert plan["next_call"]["top"] == 5
    assert not data_route.called


@pytest.mark.asyncio
async def test_country_literal_uses_quoted_eq_filter(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(META_PATH).mock(
        return_value=httpx.Response(200, json=_METADATA_JSON)
    )
    data_route = respx_mock.get(DATA_PATH)

    tools = _register(client)
    plan = await tools["smart_query"](
        model_id=MODEL, question="revenue for country Germany"
    )

    expected_clause = f"Country eq {quote_odata_string('Germany')}"
    assert expected_clause == "Country eq 'Germany'"
    assert plan["suggested_filter"] is not None
    assert expected_clause in plan["suggested_filter"]
    assert not data_route.called


@pytest.mark.asyncio
async def test_malformed_metadata_returns_error_dict(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(META_PATH).mock(
        return_value=httpx.Response(
            200,
            text=_MALFORMED_METADATA,
            headers={"content-type": "application/xml"},
        )
    )
    data_route = respx_mock.get(DATA_PATH)

    tools = _register(client)
    result = await tools["smart_query"](
        model_id=MODEL, question="2025 sales"
    )

    assert "error" in result
    assert result["code"] in {"metadata_parse_failed", "metadata_fetch_failed"}
    assert not data_route.called


@pytest.mark.asyncio
async def test_quote_odata_string_escapes_single_quotes() -> None:
    # Sanity guard: smart_query relies on quote_odata_string for safe quoting.
    assert quote_odata_string("O'Brien") == "'O''Brien'"
