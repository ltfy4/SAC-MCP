"""Tests for the aggregation tools (FactDataAggregation + client-side ops)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import aggregation
from sac_mcp.tools.aggregation import _validate

TENANT = "https://tenant.example.com"
MODEL = "Sales"
AGG_PATH = f"{TENANT}/api/v1/dataexport/providers/sac/{MODEL}/FactDataAggregation"
FACT_PATH = f"{TENANT}/api/v1/dataexport/providers/sac/{MODEL}/FactData"


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


def _capture(respx_mock: respx.MockRouter, path: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": rows})

    respx_mock.get(path).mock(side_effect=handler)
    return captured


def test_validate_rejects_unknown_op() -> None:
    with pytest.raises(ValueError, match="Invalid aggregation operator"):
        _validate([{"column": "Amount", "op": "median", "alias": "Med"}])


def test_validate_is_case_insensitive_and_defaults_alias() -> None:
    assert _validate([{"column": "Amount", "op": "SUM"}]) == [
        {"column": "Amount", "op": "sum", "alias": "SumAmount"}
    ]


@pytest.mark.asyncio
async def test_sum_runs_server_side_with_select(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured = _capture(respx_mock, AGG_PATH, [{"Region": "EMEA", "Amount": 100.0}])
    tools = _register(client)
    result = await tools["read_aggregated_data"](  # type: ignore[operator]
        model_id=MODEL,
        group_by=["Region"],
        aggregates=[{"column": "Amount", "op": "sum", "alias": "TotalAmount"}],
        filter="Year eq '2026'",
        orderby=["TotalAmount desc"],
        top=50,
    )

    assert result["aggregation"] == "server"
    assert result["rows"] == [{"Region": "EMEA", "TotalAmount": 100.0}]
    params = captured["params"]
    assert params["$select"] == "Region,Amount"
    assert params["$filter"] == "Year eq '2026'"
    assert params["$orderby"] == "Amount desc"  # alias mapped back to the measure
    assert params["$top"] == "51"  # one extra row detects has_more
    assert "$apply" not in params  # SAC silently ignores $apply


@pytest.mark.asyncio
async def test_has_more_when_server_returns_extra_row(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    _capture(respx_mock, AGG_PATH, [{"Region": r, "Amount": 1} for r in "ABC"])
    tools = _register(client)
    result = await tools["read_aggregated_data"](  # type: ignore[operator]
        model_id=MODEL,
        group_by=["Region"],
        aggregates=[{"column": "Amount", "op": "sum", "alias": "T"}],
        top=2,
    )
    assert result["row_count"] == 2
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_non_sum_ops_are_computed_client_side(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured = _capture(
        respx_mock,
        FACT_PATH,
        [
            {"Region": "EMEA", "Amount": 10.0},
            {"Region": "EMEA", "Amount": 30.0},
            {"Region": "APJ", "Amount": 5.0},
        ],
    )
    tools = _register(client)
    result = await tools["read_aggregated_data"](  # type: ignore[operator]
        model_id=MODEL,
        group_by=["Region"],
        aggregates=[
            {"column": "Amount", "op": "average", "alias": "Avg"},
            {"column": "Amount", "op": "max", "alias": "Max"},
            {"column": "Amount", "op": "count", "alias": "N"},
        ],
        orderby=["Avg desc"],
    )

    assert result["aggregation"] == "client"
    assert result["rows_scanned"] == 3
    assert result["scan_truncated"] is False
    assert result["rows"][0] == {"Region": "EMEA", "Avg": 20.0, "Max": 30.0, "N": 2}
    assert result["rows"][1] == {"Region": "APJ", "Avg": 5.0, "Max": 5.0, "N": 1}
    assert "$select" not in captured["params"]


@pytest.mark.asyncio
async def test_top_n_by_measure_orders_by_measure(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured = _capture(respx_mock, AGG_PATH, [{"Product": "P1", "Revenue": 9.0}])
    tools = _register(client)
    result = await tools["top_n_by_measure"](  # type: ignore[operator]
        model_id=MODEL, dimension="Product", measure="Revenue", direction="asc", top=5
    )
    assert result["rows"] == [{"Product": "P1", "SumRevenue": 9.0}]
    assert captured["params"]["$orderby"] == "Revenue asc"
    assert captured["params"]["$select"] == "Product,Revenue"


@pytest.mark.asyncio
async def test_aggregate_by_dimension_multiple_measures(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured = _capture(
        respx_mock, AGG_PATH, [{"Region": "EMEA", "Amount": 1.0, "Quantity": 2.0}]
    )
    tools = _register(client)
    result = await tools["aggregate_by_dimension"](  # type: ignore[operator]
        model_id=MODEL, dimension="Region", measures=["Amount", "Quantity"]
    )
    assert result["rows"] == [{"Region": "EMEA", "SumAmount": 1.0, "SumQuantity": 2.0}]
    assert captured["params"]["$select"] == "Region,Amount,Quantity"
