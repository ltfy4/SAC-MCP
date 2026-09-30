"""Tests for currency/unit tables on the Data Import API."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import currency

TENANT = "https://tenant.example.com"
CCY = f"{TENANT}/api/v1/dataimport/currencyConversions"
JOB = f"{TENANT}/api/v1/dataimport/jobs/J1"


def _register(client: SACClient) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    currency.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


@pytest.mark.asyncio
async def test_list_currency_tables(client: SACClient, respx_mock: respx.MockRouter) -> None:
    respx_mock.get(CCY).mock(return_value=httpx.Response(200, json={"value": [{"id": "FX1"}]}))
    result = await _register(client)["list_currency_tables"]()
    assert result["rows"] == [{"id": "FX1"}]


@pytest.mark.asyncio
async def test_upload_currency_rates_runs_import_job(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}
    respx_mock.get(f"{TENANT}/api/v1/csrf").mock(
        return_value=httpx.Response(200, headers={"x-csrf-token": "t"})
    )

    def create(request: httpx.Request) -> httpx.Response:
        captured["job"] = json.loads(request.content)
        return httpx.Response(200, json={"jobID": "J1"})

    def upload(request: httpx.Request) -> httpx.Response:
        captured["data"] = json.loads(request.content)
        return httpx.Response(200, json={})

    respx_mock.post(f"{CCY}/FX1").mock(side_effect=create)
    respx_mock.post(JOB).mock(side_effect=upload)
    respx_mock.post(f"{JOB}/validate").mock(
        return_value=httpx.Response(200, json={"failedNumberRows": 0})
    )
    respx_mock.post(f"{JOB}/run").mock(return_value=httpx.Response(200, json={}))
    respx_mock.get(f"{JOB}/status").mock(
        return_value=httpx.Response(200, json={"jobStatus": "COMPLETED"})
    )

    rates = [{"SourceCurrency": "EUR", "TargetCurrency": "GBP", "ExchangeRate": "0.86"}]
    result = await _register(client)["upload_currency_rates"](table_id="FX1", rates=rates)

    assert result["ran"] is True
    assert captured["job"]["JobSettings"]["importMethod"] == "Update"
    assert captured["data"] == {"Data": rates}
