"""Tests for the server-side aggregation tools."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import aggregation
from sac_mcp.tools.aggregation import _build_apply

TENANT = "https://tenant.example.com"
MODEL = "Sales"
AGG_PATH = f"{TENANT}/api/v1/dataexport/providers/sac/{MODEL}/Aggregation"


def _register(client: SACClient) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    aggregation.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


# ---- _build_apply unit tests ------------------------------------------------


def test_build_apply_with_group_by() -> None:
    result = _build_apply(
        ["Region", "Year"],
        [{"column": "Amount", "op": "sum", "alias": "TotalAmount"}],
    )
    assert result == "groupby((Region,Year),aggregate(Amount with sum as TotalAmount))"


def test_build_apply_without_group_by() -> None:
    result = _build_apply(
        [],
        [{"column": "Amount", "op": "average", "alias": "AvgAmount"}],
    )
    assert result == "aggregate(Amount with average as AvgAmount)"


def test_build_apply_multiple_aggregates() -> None:
    result = _build_apply(
        ["Region"],
        [
            {"column": "Revenue", "op": "sum", "alias": "TotalRevenue"},
            {"column": "Quantity", "op": "max", "alias": "MaxQuantity"},
        ],
    )
    assert result == (
        "groupby((Region),aggregate(Revenue with sum as TotalRevenue, "
        "Quantity with max as MaxQuantity))"
    )


def test_build_apply_invalid_op_raises() -> None:
    with pytest.raises(ValueError, match="Invalid aggregation operator"):
        _build_apply(["Region"], [{"column": "Amount", "op": "median", "alias": "Med"}])


def test_build_apply_op_case_insensitive() -> None:
    result = _build_apply([], [{"column": "Amount", "op": "SUM", "alias": "Total"}])
    assert "with sum as" in result


def test_build_apply_countdistinct() -> None:
    result = _build_apply(
        ["Product"],
        [{"column": "CustomerId", "op": "countdistinct", "alias": "UniqueCustomers"}],
    )
    assert "CustomerId with countdistinct as UniqueCustomers" in result


# ---- read_aggregated_data ---------------------------------------------------


@pytest.mark.asyncio
async def test_read_aggregated_data_builds_correct_apply(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": [{"Region": "EMEA", "TotalAmount": 100}]})

    respx_mock.get(AGG_PATH).mock(side_effect=handler)

    tools = _register(client)
    result = await tools["read_aggregated_data"](  # type: ignore[operator]
        model_id=MODEL,
        group_by=["Region"],
        aggregates=[{"column": "Amount", "op": "sum", "alias": "TotalAmount"}],
        top=50,
    )

    assert result["row_count"] == 1
    assert result["rows"][0]["Region"] == "EMEA"
    params = captured["params"]
    assert params["$apply"] == "groupby((Region),aggregate(Amount with sum as TotalAmount))"
    assert params["$top"] == "50"


@pytest.mark.asyncio
async def test_read_aggregated_data_passes_filter(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": []})

    respx_mock.get(AGG_PATH).mock(side_effect=handler)

    tools = _register(client)
    await tools["read_aggregated_data"](  # type: ignore[operator]
        model_id=MODEL,
        group_by=["Region"],
        aggregates=[{"column": "Amount", "op": "sum", "alias": "TotalAmount"}],
        filter="Year eq '2025'",
    )

    assert captured["params"]["$filter"] == "Year eq '2025'"


@pytest.mark.asyncio
async def test_read_aggregated_data_passes_orderby(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": []})

    respx_mock.get(AGG_PATH).mock(side_effect=handler)

    tools = _register(client)
    await tools["read_aggregated_data"](  # type: ignore[operator]
        model_id=MODEL,
        group_by=["Region"],
        aggregates=[{"column": "Amount", "op": "sum", "alias": "TotalAmount"}],
        orderby=["TotalAmount desc"],
    )

    assert captured["params"]["$orderby"] == "TotalAmount desc"


# ---- top_n_by_measure -------------------------------------------------------


@pytest.mark.asyncio
async def test_top_n_by_measure_builds_apply_with_orderby(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": [{"Region": "EMEA", "SumAmount": 500}]})

    respx_mock.get(AGG_PATH).mock(side_effect=handler)

    tools = _register(client)
    result = await tools["top_n_by_measure"](  # type: ignore[operator]
        model_id=MODEL,
        dimension="Region",
        measure="Amount",
        agg="sum",
        direction="desc",
        top=5,
    )

    assert result["row_count"] == 1
    params = captured["params"]
    assert params["$apply"] == "groupby((Region),aggregate(Amount with sum as SumAmount))"
    assert params["$orderby"] == "SumAmount desc"
    assert params["$top"] == "5"


@pytest.mark.asyncio
async def test_top_n_by_measure_asc_direction(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": []})

    respx_mock.get(AGG_PATH).mock(side_effect=handler)

    tools = _register(client)
    await tools["top_n_by_measure"](  # type: ignore[operator]
        model_id=MODEL,
        dimension="Product",
        measure="Revenue",
        agg="average",
        direction="asc",
        top=3,
    )

    params = captured["params"]
    assert params["$orderby"] == "AverageRevenue asc"
    assert "Revenue with average as AverageRevenue" in params["$apply"]


# ---- aggregate_by_dimension -------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_by_dimension_multiple_measures(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": [{"Region": "US", "SumRevenue": 1000, "SumCost": 400}]})

    respx_mock.get(AGG_PATH).mock(side_effect=handler)

    tools = _register(client)
    result = await tools["aggregate_by_dimension"](  # type: ignore[operator]
        model_id=MODEL,
        dimension="Region",
        measures=["Revenue", "Cost"],
        agg="sum",
    )

    assert result["row_count"] == 1
    params = captured["params"]
    apply = params["$apply"]
    assert "Revenue with sum as SumRevenue" in apply
    assert "Cost with sum as SumCost" in apply
    assert apply.startswith("groupby((Region),")


@pytest.mark.asyncio
async def test_aggregate_by_dimension_passes_filter(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": []})

    respx_mock.get(AGG_PATH).mock(side_effect=handler)

    tools = _register(client)
    await tools["aggregate_by_dimension"](  # type: ignore[operator]
        model_id=MODEL,
        dimension="Product",
        measures=["Amount"],
        agg="min",
        filter="Year eq '2024'",
    )

    assert captured["params"]["$filter"] == "Year eq '2024'"
    assert "Amount with min as MinAmount" in captured["params"]["$apply"]
