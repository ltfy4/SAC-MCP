"""Tests for the model monitoring tools."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import monitoring

TENANT = "https://tenant.example.com"
MODELS_PATH = f"{TENANT}/api/v1/monitoring/models"
MODEL = "Sales"
DETAIL_PATH = f"{TENANT}/api/v1/monitoring/models/{MODEL}"
HISTORY_PATH = f"{TENANT}/api/v1/monitoring/models/{MODEL}/jobHistory"


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


# ---- list_monitored_models --------------------------------------------------


@pytest.mark.asyncio
async def test_list_monitored_models_returns_rows(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(MODELS_PATH).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"modelId": MODEL, "rowCount": 1000, "size": 204800},
                ]
            },
        )
    )

    tools = _register(client)
    result = await tools["list_monitored_models"]()  # type: ignore[operator]

    assert result["row_count"] == 1
    assert result["rows"][0]["modelId"] == MODEL
    assert result["rows"][0]["rowCount"] == 1000


@pytest.mark.asyncio
async def test_list_monitored_models_passes_top_and_filter(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": []})

    respx_mock.get(MODELS_PATH).mock(side_effect=handler)

    tools = _register(client)
    await tools["list_monitored_models"](top=10, filter="rowCount gt 0")  # type: ignore[operator]

    assert captured["params"]["$top"] == "10"
    assert captured["params"]["$filter"] == "rowCount gt 0"


# ---- get_model_monitoring ---------------------------------------------------


@pytest.mark.asyncio
async def test_get_model_monitoring_returns_detail(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    payload = {
        "modelId": MODEL,
        "rowCount": 5000,
        "size": 1048576,
        "lastImportTime": "2026-05-14T10:00:00Z",
        "lastModifiedBy": "admin",
    }
    respx_mock.get(DETAIL_PATH).mock(return_value=httpx.Response(200, json=payload))

    tools = _register(client)
    result = await tools["get_model_monitoring"](model_id=MODEL)  # type: ignore[operator]

    assert result["modelId"] == MODEL
    assert result["rowCount"] == 5000
    assert result["lastModifiedBy"] == "admin"


# ---- get_model_job_history --------------------------------------------------


@pytest.mark.asyncio
async def test_get_model_job_history_returns_rows(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(HISTORY_PATH).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"jobId": "j1", "status": "SUCCESS", "startTime": "2026-05-14T09:00:00Z"},
                    {"jobId": "j2", "status": "FAILED", "startTime": "2026-05-13T08:00:00Z"},
                ]
            },
        )
    )

    tools = _register(client)
    result = await tools["get_model_job_history"](model_id=MODEL)  # type: ignore[operator]

    assert result["row_count"] == 2
    assert result["rows"][0]["jobId"] == "j1"


@pytest.mark.asyncio
async def test_get_model_job_history_passes_top(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": []})

    respx_mock.get(HISTORY_PATH).mock(side_effect=handler)

    tools = _register(client)
    await tools["get_model_job_history"](model_id=MODEL, top=5)  # type: ignore[operator]

    assert captured["params"]["$top"] == "5"
    assert "$filter" not in captured["params"]


@pytest.mark.asyncio
async def test_get_model_job_history_since_iso_sets_filter(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": []})

    respx_mock.get(HISTORY_PATH).mock(side_effect=handler)

    tools = _register(client)
    await tools["get_model_job_history"](  # type: ignore[operator]
        model_id=MODEL, since_iso="2026-05-01T00:00:00Z"
    )

    assert "$filter" in captured["params"]
    assert "startTime" in captured["params"]["$filter"]
    assert "2026-05-01T00:00:00Z" in captured["params"]["$filter"]
