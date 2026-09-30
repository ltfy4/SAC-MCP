"""Tests for model monitoring (content-type-aware reader)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import monitoring

TENANT = "https://tenant.example.com"


def _register(client: SACClient) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    monitoring.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


@pytest.mark.asyncio
async def test_get_model_monitoring_parses_csv(client: SACClient, respx_mock: respx.MockRouter) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["accept"] = request.headers.get("accept")
        return httpx.Response(
            200, text="modelId,rowCount\nM1,42\n", headers={"content-type": "text/csv"}
        )

    respx_mock.get(f"{TENANT}/api/v1/monitoring/M1").mock(side_effect=handler)
    result = await _register(client)["get_model_monitoring"](model_id="M1")

    assert result["rows"] == [{"modelId": "M1", "rowCount": "42"}]
    assert "text/csv" in captured["accept"]  # JSON-only Accept gets 406 from SAC


@pytest.mark.asyncio
async def test_get_model_monitoring_parses_json(client: SACClient, respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{TENANT}/api/v1/monitoring/M1").mock(
        return_value=httpx.Response(200, json={"rowCount": 42})
    )
    result = await _register(client)["get_model_monitoring"](model_id="M1")
    assert result["data"] == {"rowCount": 42}
