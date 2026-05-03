"""Tests for the currency / unit conversion tool surface."""

from __future__ import annotations

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import currency

TENANT = "https://tenant.example.com"


def _register(client: SACClient) -> dict[str, object]:
    captured: dict[str, object] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    currency.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


@pytest.mark.asyncio
async def test_list_currency_tables(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{TENANT}/api/v1/currencyConversion").mock(
        return_value=httpx.Response(200, json={"value": [{"id": "RATES_2024"}]})
    )
    tools = _register(client)
    result = await tools["list_currency_tables"]()  # type: ignore[operator]
    assert result["row_count"] == 1
    assert result["rows"][0]["id"] == "RATES_2024"


@pytest.mark.asyncio
async def test_get_currency_rates(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(
        f"{TENANT}/api/v1/currencyConversion/RATES_2024/rates",
        params={"$top": "50"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={"value": [{"sourceCurrency": "USD", "targetCurrency": "EUR", "rate": 0.92}]},
        )
    )
    tools = _register(client)
    result = await tools["get_currency_rates"](table_id="RATES_2024", top=50)  # type: ignore[operator]
    assert result["row_count"] == 1
    assert result["rows"][0]["sourceCurrency"] == "USD"


@pytest.mark.asyncio
async def test_upload_currency_rates(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{TENANT}/api/v1/csrf").mock(
        return_value=httpx.Response(200, headers={"x-csrf-token": "T1"}, json={})
    )
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["csrf"] = request.headers.get("x-csrf-token")
        return httpx.Response(200, json={"uploaded": 2})

    respx_mock.post(
        f"{TENANT}/api/v1/currencyConversion/RATES_2024/rates"
    ).mock(side_effect=handler)

    tools = _register(client)
    rates = [
        {"sourceCurrency": "USD", "targetCurrency": "EUR", "rate": 0.92},
        {"sourceCurrency": "USD", "targetCurrency": "GBP", "rate": 0.79},
    ]
    result = await tools["upload_currency_rates"](  # type: ignore[operator]
        table_id="RATES_2024", rates=rates
    )
    assert result["uploaded"] == 2
    assert captured["csrf"] == "T1"
    assert b"USD" in captured["body"]  # type: ignore[operator]


@pytest.mark.asyncio
async def test_list_unit_tables(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{TENANT}/api/v1/unitConversion").mock(
        return_value=httpx.Response(200, json=[{"id": "UOM_GLOBAL"}])
    )
    tools = _register(client)
    result = await tools["list_unit_tables"]()  # type: ignore[operator]
    assert result["row_count"] == 1
    assert result["rows"][0]["id"] == "UOM_GLOBAL"


@pytest.mark.asyncio
async def test_read_currency_data(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": [{"Currency": "EUR", "Rate": 1.0}]})

    respx_mock.get(
        f"{TENANT}/api/v1/dataexport/providers/sac/MODEL1/CurrencyData"
    ).mock(side_effect=handler)

    tools = _register(client)
    result = await tools["read_currency_data"](  # type: ignore[operator]
        model_id="MODEL1", top=10, filter="Currency eq 'EUR'"
    )
    assert result["row_count"] == 1
    assert captured["params"]["$filter"] == "Currency eq 'EUR'"  # type: ignore[index]
