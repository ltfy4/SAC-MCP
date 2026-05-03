"""Tests for the sql-query router."""

from __future__ import annotations

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import sql_query
from sac_mcp.tools.sql_query import _is_analytical, _parse_simple_query

TENANT = "https://tenant.example.com"


def _register(client: SACClient) -> dict[str, object]:
    captured: dict[str, object] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    sql_query.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


# ---- pure-function parser tests --------------------------------------


def test_is_analytical_detects_sum() -> None:
    assert _is_analytical("SUM(Amount) GROUP BY Region") is True


def test_is_analytical_detects_group_by() -> None:
    assert _is_analytical("select * group by Region") is True


def test_is_analytical_false_for_simple() -> None:
    assert _is_analytical("Region eq 'EMEA'") is False


def test_parse_simple_query_full() -> None:
    parsed = _parse_simple_query(
        "SELECT col1, col2 FROM model WHERE Region eq 'EMEA' ORDER BY Date TOP 50"
    )
    assert parsed["filter"] == "Region eq 'EMEA'"
    assert parsed["select"] == "col1, col2"
    assert parsed["orderby"] == "Date"
    assert parsed["top"] == 50


def test_parse_simple_query_filter_only() -> None:
    parsed = _parse_simple_query("Region eq 'EMEA'")
    assert parsed["filter"] == "Region eq 'EMEA'"
    assert "select" not in parsed
    assert "orderby" not in parsed
    assert "top" not in parsed


# ---- routing tests ---------------------------------------------------


@pytest.mark.asyncio
async def test_sql_query_routes_to_odata(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": [{"id": 1}]})

    respx_mock.get(
        f"{TENANT}/api/v1/dataexport/providers/sac/M1/FactData"
    ).mock(side_effect=handler)

    tools = _register(client)
    result = await tools["sql_query"](  # type: ignore[operator]
        model_id="M1", query="Region eq 'EMEA' TOP 10"
    )
    assert result["route"] == "odata_export"
    params = captured["params"]
    assert params["$filter"] == "Region eq 'EMEA'"  # type: ignore[index]
    assert params["$top"] == "10"  # type: ignore[index]


@pytest.mark.asyncio
async def test_sql_query_routes_to_widget_with_story(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{TENANT}/widgetquery/getWidgetData").mock(
        return_value=httpx.Response(200, json={"value": 100})
    )
    tools = _register(client)
    result = await tools["sql_query"](  # type: ignore[operator]
        model_id="M1",
        query="SUM(Amount) GROUP BY Region",
        story_id="S1",
        widget_id="Chart_1",
    )
    assert result["route"] == "widget_query"
    assert result["value"] == 100


@pytest.mark.asyncio
async def test_sql_query_analytical_no_story_falls_back(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(
        f"{TENANT}/api/v1/dataexport/providers/sac/M1/FactData"
    ).mock(return_value=httpx.Response(200, json={"value": [{"id": 1}]}))

    tools = _register(client)
    result = await tools["sql_query"](  # type: ignore[operator]
        model_id="M1", query="SUM(Amount) GROUP BY Region"
    )
    assert result["route"] == "odata_export"
    assert "note" in result
