"""Tests for the Data Action tools."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import dataactions

TENANT = "https://tenant.example.com"
LIST_PATH = f"{TENANT}/api/v1/dataactions"
DA = "DA_COPY_ACTUALS"
DETAIL_PATH = f"{TENANT}/api/v1/dataactions/{DA}"
EXECUTIONS_PATH = f"{TENANT}/api/v1/dataactions/{DA}/executions"
CSRF_PATH = f"{TENANT}/api/v1/csrf"


def _register(client: SACClient) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    dataactions.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


def _mock_csrf(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(CSRF_PATH).mock(
        return_value=httpx.Response(200, headers={"x-csrf-token": "csrf-tok"})
    )


# ---- list_data_actions ------------------------------------------------------


@pytest.mark.asyncio
async def test_list_data_actions_returns_rows(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(LIST_PATH).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"id": DA, "name": "Copy Actuals", "modelId": "Sales"},
                ]
            },
        )
    )

    tools = _register(client)
    result = await tools["list_data_actions"]()  # type: ignore[operator]

    assert result["row_count"] == 1
    assert result["rows"][0]["id"] == DA


@pytest.mark.asyncio
async def test_list_data_actions_passes_top_and_model_id(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"value": []})

    respx_mock.get(LIST_PATH).mock(side_effect=handler)

    tools = _register(client)
    await tools["list_data_actions"](top=10, model_id="Sales")  # type: ignore[operator]

    assert captured["params"]["$top"] == "10"
    assert captured["params"]["modelId"] == "Sales"


# ---- get_data_action --------------------------------------------------------


@pytest.mark.asyncio
async def test_get_data_action_returns_detail(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    payload = {
        "id": DA,
        "name": "Copy Actuals",
        "parameters": [{"parameterId": "TargetVersion", "type": "version"}],
    }
    respx_mock.get(DETAIL_PATH).mock(return_value=httpx.Response(200, json=payload))

    tools = _register(client)
    result = await tools["get_data_action"](data_action_id=DA)  # type: ignore[operator]

    assert result["id"] == DA
    assert result["parameters"][0]["parameterId"] == "TargetVersion"


# ---- run_data_action --------------------------------------------------------


@pytest.mark.asyncio
async def test_run_data_action_posts_parameter_values(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    _mock_csrf(respx_mock)
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"executionId": "ex-1", "status": "RUNNING"})

    respx_mock.post(EXECUTIONS_PATH).mock(side_effect=handler)

    tools = _register(client)
    result = await tools["run_data_action"](  # type: ignore[operator]
        data_action_id=DA,
        parameter_values=[{"parameterId": "TargetVersion", "value": "public.Actual"}],
    )

    assert result["executionId"] == "ex-1"
    assert captured["body"]["parameterValues"][0]["parameterId"] == "TargetVersion"


@pytest.mark.asyncio
async def test_run_data_action_without_parameters_sends_empty_body(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    _mock_csrf(respx_mock)
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"executionId": "ex-2"})

    respx_mock.post(EXECUTIONS_PATH).mock(side_effect=handler)

    tools = _register(client)
    result = await tools["run_data_action"](data_action_id=DA)  # type: ignore[operator]

    assert result["executionId"] == "ex-2"
    assert captured["body"] == {}


@pytest.mark.asyncio
async def test_run_data_action_surfaces_sac_error(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    _mock_csrf(respx_mock)
    respx_mock.post(EXECUTIONS_PATH).mock(
        return_value=httpx.Response(
            404, json={"error": {"code": "NOT_FOUND", "message": "no such data action"}}
        )
    )

    tools = _register(client)
    result = await tools["run_data_action"](data_action_id=DA)  # type: ignore[operator]

    assert "error" in result
    assert result["status"] == 404


# ---- list_data_action_executions / get_data_action_status -------------------


@pytest.mark.asyncio
async def test_list_data_action_executions_returns_rows(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(EXECUTIONS_PATH).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"executionId": "ex-1", "status": "COMPLETED"},
                    {"executionId": "ex-2", "status": "FAILED"},
                ]
            },
        )
    )

    tools = _register(client)
    result = await tools["list_data_action_executions"](data_action_id=DA)  # type: ignore[operator]

    assert result["row_count"] == 2
    assert result["rows"][1]["status"] == "FAILED"


@pytest.mark.asyncio
async def test_get_data_action_status_returns_execution(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{TENANT}/api/v1/dataactions/executions/ex-1").mock(
        return_value=httpx.Response(
            200, json={"executionId": "ex-1", "status": "COMPLETED"}
        )
    )

    tools = _register(client)
    result = await tools["get_data_action_status"](execution_id="ex-1")  # type: ignore[operator]

    assert result["status"] == "COMPLETED"
