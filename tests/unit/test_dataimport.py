"""Tests for the Data Import tools (one-shot write_fact_data and helpers)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from sac_mcp.client.http import SACClient
from sac_mcp.tools import dataimport

TENANT = "https://tenant.example.com"
MODEL = "Sales"
CREATE_PATH = f"{TENANT}/api/v1/dataimport/models/{MODEL}/factData"
JOB = "job-1"
DATA_PATH = f"{TENANT}/api/v1/dataimport/jobs/{JOB}/data"
VALIDATE_PATH = f"{TENANT}/api/v1/dataimport/jobs/{JOB}/validate"
RUN_PATH = f"{TENANT}/api/v1/dataimport/jobs/{JOB}/run"
STATUS_PATH = f"{TENANT}/api/v1/dataimport/jobs/{JOB}/status"
INVALID_ROWS_PATH = f"{TENANT}/api/v1/dataimport/jobs/{JOB}/invalidRows"
ALL_JOBS_PATH = f"{TENANT}/api/v1/dataimport/jobs"
METADATA_PATH = f"{TENANT}/api/v1/dataimport/models/{MODEL}/metadata"
CSRF_PATH = f"{TENANT}/api/v1/csrf"

ROWS = [
    {"Date": "202601", "Region": "EMEA", "Amount": "100"},
    {"Date": "202601", "Region": "APJ", "Amount": "250"},
]


def _register(client: SACClient) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _Stub:
        def tool(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            def deco(fn):  # type: ignore[no-untyped-def]
                captured[fn.__name__] = fn
                return fn

            return deco

    dataimport.register(_Stub(), client)  # type: ignore[arg-type]
    return captured


def _mock_csrf(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(CSRF_PATH).mock(
        return_value=httpx.Response(200, headers={"x-csrf-token": "csrf-tok"})
    )


def _mock_happy_lifecycle(respx_mock: respx.MockRouter) -> dict[str, Any]:
    """Mock create→upload→validate→run→status; capture upload chunks."""

    captured: dict[str, Any] = {"chunks": []}
    _mock_csrf(respx_mock)
    respx_mock.post(CREATE_PATH).mock(
        return_value=httpx.Response(200, json={"jobID": JOB})
    )

    def data_handler(request: httpx.Request) -> httpx.Response:
        captured["chunks"].append(json.loads(request.content)["data"])
        return httpx.Response(200, json={})

    respx_mock.post(DATA_PATH).mock(side_effect=data_handler)
    respx_mock.post(VALIDATE_PATH).mock(
        return_value=httpx.Response(
            200, json={"totalNumberRows": 2, "failedNumberRows": 0}
        )
    )
    respx_mock.post(RUN_PATH).mock(
        return_value=httpx.Response(200, json={"status": "RUNNING"})
    )
    respx_mock.get(STATUS_PATH).mock(
        return_value=httpx.Response(200, json={"jobStatus": "COMPLETED"})
    )
    return captured


# ---- write_fact_data --------------------------------------------------------


@pytest.mark.asyncio
async def test_write_fact_data_runs_full_lifecycle(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured = _mock_happy_lifecycle(respx_mock)

    tools = _register(client)
    result = await tools["write_fact_data"](model_id=MODEL, rows=ROWS)  # type: ignore[operator]

    assert result["job_id"] == JOB
    assert result["ran"] is True
    assert result["rows_uploaded"] == 2
    assert result["job_status"] == {"jobStatus": "COMPLETED"}
    assert captured["chunks"] == [ROWS]


@pytest.mark.asyncio
async def test_write_fact_data_uploads_in_chunks(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured = _mock_happy_lifecycle(respx_mock)
    rows = [{"n": str(i)} for i in range(5)]

    tools = _register(client)
    result = await tools["write_fact_data"](  # type: ignore[operator]
        model_id=MODEL, rows=rows, chunk_size=2
    )

    assert result["ran"] is True
    assert [len(c) for c in captured["chunks"]] == [2, 2, 1]


@pytest.mark.asyncio
async def test_write_fact_data_accepts_csv(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    captured = _mock_happy_lifecycle(respx_mock)
    csv_text = "Date,Region,Amount\n202601,EMEA,100\n202601,APJ,250\n"

    tools = _register(client)
    result = await tools["write_fact_data"](model_id=MODEL, csv_text=csv_text)  # type: ignore[operator]

    assert result["ran"] is True
    assert captured["chunks"][0][0] == {"Date": "202601", "Region": "EMEA", "Amount": "100"}


@pytest.mark.asyncio
async def test_write_fact_data_stops_on_validation_failures(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    _mock_csrf(respx_mock)
    respx_mock.post(CREATE_PATH).mock(
        return_value=httpx.Response(200, json={"jobID": JOB})
    )
    respx_mock.post(DATA_PATH).mock(return_value=httpx.Response(200, json={}))
    respx_mock.post(VALIDATE_PATH).mock(
        return_value=httpx.Response(
            200, json={"totalNumberRows": 2, "failedNumberRows": 1}
        )
    )
    run_route = respx_mock.post(RUN_PATH).mock(
        return_value=httpx.Response(200, json={})
    )

    tools = _register(client)
    result = await tools["write_fact_data"](model_id=MODEL, rows=ROWS)  # type: ignore[operator]

    assert result["ran"] is False
    assert result["job_id"] == JOB
    assert "get_job_invalid_rows" in result["hint"]
    assert not run_route.called


@pytest.mark.asyncio
async def test_write_fact_data_stops_when_only_secondary_count_key_reports_failures(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    # An empty failedRows list next to a non-zero invalidRowCount must still
    # stop the run — no key may short-circuit the check.
    _mock_csrf(respx_mock)
    respx_mock.post(CREATE_PATH).mock(
        return_value=httpx.Response(200, json={"jobID": JOB})
    )
    respx_mock.post(DATA_PATH).mock(return_value=httpx.Response(200, json={}))
    respx_mock.post(VALIDATE_PATH).mock(
        return_value=httpx.Response(
            200, json={"failedRows": [], "invalidRowCount": 5}
        )
    )
    run_route = respx_mock.post(RUN_PATH).mock(
        return_value=httpx.Response(200, json={})
    )

    tools = _register(client)
    result = await tools["write_fact_data"](model_id=MODEL, rows=ROWS)  # type: ignore[operator]

    assert result["ran"] is False
    assert not run_route.called


@pytest.mark.asyncio
async def test_write_fact_data_requires_rows_or_csv(client: SACClient) -> None:
    tools = _register(client)
    result = await tools["write_fact_data"](model_id=MODEL)  # type: ignore[operator]

    assert "error" in result


@pytest.mark.asyncio
async def test_write_fact_data_surfaces_job_id_on_mid_lifecycle_error(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    _mock_csrf(respx_mock)
    respx_mock.post(CREATE_PATH).mock(
        return_value=httpx.Response(200, json={"jobID": JOB})
    )
    respx_mock.post(DATA_PATH).mock(
        return_value=httpx.Response(
            400, json={"error": {"code": "BAD_DATA", "message": "column mismatch"}}
        )
    )

    tools = _register(client)
    result = await tools["write_fact_data"](model_id=MODEL, rows=ROWS)  # type: ignore[operator]

    assert "error" in result
    assert result["job_id"] == JOB
    assert "cancel_job" in result["hint"]


@pytest.mark.asyncio
async def test_write_fact_data_errors_when_no_job_id_returned(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    _mock_csrf(respx_mock)
    respx_mock.post(CREATE_PATH).mock(
        return_value=httpx.Response(200, json={"unexpected": "shape"})
    )

    tools = _register(client)
    result = await tools["write_fact_data"](model_id=MODEL, rows=ROWS)  # type: ignore[operator]

    assert "error" in result
    assert result["response"] == {"unexpected": "shape"}


# ---- get_job_invalid_rows ---------------------------------------------------


@pytest.mark.asyncio
async def test_get_job_invalid_rows_unwraps_dict_payload(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(INVALID_ROWS_PATH).mock(
        return_value=httpx.Response(
            200,
            json={"invalidRows": [{"row": 7, "reason": "unknown member 'XX'"}]},
        )
    )

    tools = _register(client)
    result = await tools["get_job_invalid_rows"](job_id=JOB)  # type: ignore[operator]

    assert result["row_count"] == 1
    assert result["rows"][0]["reason"] == "unknown member 'XX'"


@pytest.mark.asyncio
async def test_get_job_invalid_rows_accepts_bare_list_payload(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(INVALID_ROWS_PATH).mock(
        return_value=httpx.Response(200, json=[{"row": 1}, {"row": 2}])
    )

    tools = _register(client)
    result = await tools["get_job_invalid_rows"](job_id=JOB)  # type: ignore[operator]

    assert result["row_count"] == 2


# ---- list_all_import_jobs / get_import_metadata -----------------------------


@pytest.mark.asyncio
async def test_list_all_import_jobs_returns_envelope(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(ALL_JOBS_PATH).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {"jobID": JOB, "modelId": MODEL, "status": "COMPLETED"},
                    {"jobID": "job-2", "modelId": "HR", "status": "FAILED"},
                ]
            },
        )
    )

    tools = _register(client)
    result = await tools["list_all_import_jobs"]()  # type: ignore[operator]

    assert result["row_count"] == 2
    assert result["rows"][0]["jobID"] == JOB


@pytest.mark.asyncio
async def test_get_import_metadata_returns_columns(
    client: SACClient, respx_mock: respx.MockRouter
) -> None:
    payload = {
        "factData": {
            "columns": [
                {"columnName": "Date", "columnDataType": "date"},
                {"columnName": "Amount", "columnDataType": "decimal"},
            ]
        }
    }
    respx_mock.get(METADATA_PATH).mock(return_value=httpx.Response(200, json=payload))

    tools = _register(client)
    result = await tools["get_import_metadata"](model_id=MODEL)  # type: ignore[operator]

    assert result["factData"]["columns"][0]["columnName"] == "Date"
