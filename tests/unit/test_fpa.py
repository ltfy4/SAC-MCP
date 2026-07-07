"""Tests for the FP&A analysis tools."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import fpa

TENANT = "https://tenant.example.com"
MODEL = "Finance"
AGG_PATH = f"{TENANT}/api/v1/dataexport/providers/sac/{MODEL}/Aggregation"
VERSION_MD_PATH = f"{TENANT}/api/v1/dataexport/providers/sac/{MODEL}/VersionMasterData"
CC_MD_PATH = f"{TENANT}/api/v1/dataexport/providers/sac/{MODEL}/CostCenterMasterData"


def _register(client: SACClient) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    fpa.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


# ---- list_versions ----------------------------------------------------------


@pytest.mark.asyncio
async def test_list_versions_returns_members(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(VERSION_MD_PATH).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"ID": "public.Actual", "Description": "Actual"},
                    {"ID": "public.Plan", "Description": "Plan"},
                ]
            },
        )
    )

    tools = _register(client)
    result = await tools["list_versions"](model_id=MODEL)  # type: ignore[operator]

    assert result["row_count"] == 2
    assert result["rows"][0]["ID"] == "public.Actual"


# ---- compare_versions -------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_versions_computes_variance(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        f = request.url.params["$filter"]
        if "public.Actual" in f:
            rows = [
                {"CostCenter": "CC1", "Value": "120"},
                {"CostCenter": "CC2", "Value": "80"},
            ]
        else:
            rows = [
                {"CostCenter": "CC1", "Value": "100"},
                {"CostCenter": "CC3", "Value": "50"},
            ]
        return httpx.Response(200, json={"value": rows})

    respx_mock.get(AGG_PATH).mock(side_effect=handler)

    tools = _register(client)
    result = await tools["compare_versions"](  # type: ignore[operator]
        model_id=MODEL,
        measure="Amount",
        group_by=["CostCenter"],
        version_a="public.Actual",
        version_b="public.Plan",
    )

    by_cc = {r["CostCenter"]: r for r in result["rows"]}
    assert by_cc["CC1"]["variance"] == 20.0
    assert by_cc["CC1"]["variance_pct"] == 20.0
    # Present only in one version → variance is None, row still reported.
    assert by_cc["CC2"]["version_b"] is None
    assert by_cc["CC2"]["variance"] is None
    assert by_cc["CC3"]["version_a"] is None
    assert result["versions"] == {
        "version_a": "public.Actual",
        "version_b": "public.Plan",
    }


@pytest.mark.asyncio
async def test_compare_versions_combines_extra_filter_and_quotes_versions(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    filters: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        filters.append(request.url.params["$filter"])
        return httpx.Response(200, json={"value": []})

    respx_mock.get(AGG_PATH).mock(side_effect=handler)

    tools = _register(client)
    await tools["compare_versions"](  # type: ignore[operator]
        model_id=MODEL,
        measure="Amount",
        group_by=["CostCenter"],
        version_a="O'Brien",
        version_b="public.Plan",
        filter="Year eq '2026'",
    )

    assert any("Version eq 'O''Brien'" in f for f in filters)
    assert all("Year eq '2026'" in f for f in filters)


# ---- measure_trend ----------------------------------------------------------


@pytest.mark.asyncio
async def test_measure_trend_orders_chronologically_and_computes_change(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    # SAC returns newest first (we request `$orderby=Date desc`).
    respx_mock.get(AGG_PATH).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"Date": "202603", "Value": "150"},
                    {"Date": "202602", "Value": "100"},
                    {"Date": "202601", "Value": "80"},
                ]
            },
        )
    )

    tools = _register(client)
    result = await tools["measure_trend"](  # type: ignore[operator]
        model_id=MODEL, measure="Amount", periods=3
    )

    periods = [r["period"] for r in result["rows"]]
    assert periods == ["202601", "202602", "202603"]
    assert result["rows"][0]["change"] is None
    assert result["rows"][1]["change"] == 20.0
    assert result["rows"][1]["change_pct"] == 25.0
    assert result["rows"][2]["change"] == 50.0


@pytest.mark.asyncio
async def test_measure_trend_passes_orderby_and_top(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": []})

    respx_mock.get(AGG_PATH).mock(side_effect=handler)

    tools = _register(client)
    await tools["measure_trend"](  # type: ignore[operator]
        model_id=MODEL, measure="Amount", time_dimension="Month", periods=6
    )

    assert captured["params"]["$orderby"] == "Month desc"
    assert captured["params"]["$top"] == "6"
    assert "groupby((Month)" in captured["params"]["$apply"]


# ---- check_data_completeness ------------------------------------------------


@pytest.mark.asyncio
async def test_check_data_completeness_reports_missing_members(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(CC_MD_PATH).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"ID": "CC1"},
                    {"ID": "CC2"},
                    {"ID": "CC3"},
                ]
            },
        )
    )
    respx_mock.get(AGG_PATH).mock(
        return_value=httpx.Response(
            200,
            json={"value": [{"CostCenter": "CC1", "N": 12}]},
        )
    )

    tools = _register(client)
    result = await tools["check_data_completeness"](  # type: ignore[operator]
        model_id=MODEL,
        dimension="CostCenter",
        measure="Amount",
        filter="Version eq 'public.Plan'",
    )

    assert result["total_members"] == 3
    assert result["members_with_data"] == 1
    assert result["missing_count"] == 2
    assert result["members_missing_data"] == ["CC2", "CC3"]
    assert result["filter"] == "Version eq 'public.Plan'"
