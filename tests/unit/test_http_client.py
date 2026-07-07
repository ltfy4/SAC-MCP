"""SACClient end-to-end behaviour with mocked transport."""

from __future__ import annotations

import httpx
import pytest
import respx

from sac_mcp.client.errors import SACError
from sac_mcp.client.http import SACClient
from sac_mcp.config import get_settings

TENANT = "https://tenant.example.com"
AUTH = "https://auth.example.com"


def _oauth_route(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.post(f"{AUTH}/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
    )


@pytest.mark.asyncio
async def test_get_attaches_bearer_and_custom_auth_header(respx_mock: respx.MockRouter) -> None:
    _oauth_route(respx_mock)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"value": [{"id": 1}]})

    respx_mock.get(f"{TENANT}/api/v1/stories").mock(side_effect=handler)

    async with SACClient(get_settings()) as client:
        out = await client.get_json("/api/v1/stories")

    assert out == {"value": [{"id": 1}]}
    assert captured["headers"]["authorization"] == "Bearer tok"
    assert captured["headers"]["x-sap-sac-custom-auth"] == "true"


@pytest.mark.asyncio
async def test_post_fetches_and_attaches_csrf(respx_mock: respx.MockRouter) -> None:
    _oauth_route(respx_mock)
    respx_mock.get(f"{TENANT}/api/v1/csrf").mock(
        return_value=httpx.Response(200, headers={"x-csrf-token": "CSRF1"}, json={})
    )
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"jobId": "j1"})

    respx_mock.post(f"{TENANT}/api/v1/dataimport/models/M/factData").mock(side_effect=handler)

    async with SACClient(get_settings()) as client:
        out = await client.post_json(
            "/api/v1/dataimport/models/M/factData", json={"importMethod": "Update"}
        )

    assert out == {"jobId": "j1"}
    assert captured["headers"]["x-csrf-token"] == "CSRF1"


@pytest.mark.asyncio
async def test_csrf_refresh_on_403(respx_mock: respx.MockRouter) -> None:
    _oauth_route(respx_mock)
    csrf_route = respx_mock.get(f"{TENANT}/api/v1/csrf").mock(
        side_effect=[
            httpx.Response(200, headers={"x-csrf-token": "OLD"}, json={}),
            httpx.Response(200, headers={"x-csrf-token": "NEW"}, json={}),
        ]
    )

    seen_tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_tokens.append(request.headers["x-csrf-token"])
        if request.headers["x-csrf-token"] == "OLD":
            return httpx.Response(
                403,
                headers={"x-csrf-token": "Required"},
                json={"error": {"code": "CSRF_TOKEN_BAD", "message": "csrf required"}},
            )
        return httpx.Response(200, json={"ok": True})

    respx_mock.post(f"{TENANT}/api/v1/foo").mock(side_effect=handler)

    async with SACClient(get_settings()) as client:
        out = await client.post_json("/api/v1/foo", json={})

    assert out == {"ok": True}
    assert seen_tokens == ["OLD", "NEW"]
    assert csrf_route.call_count == 2


@pytest.mark.asyncio
async def test_4xx_raises_sac_error(respx_mock: respx.MockRouter) -> None:
    _oauth_route(respx_mock)
    respx_mock.get(f"{TENANT}/api/v1/missing").mock(
        return_value=httpx.Response(404, json={"error": {"code": "NotFound", "message": "nope"}})
    )
    async with SACClient(get_settings()) as client:
        with pytest.raises(SACError) as exc:
            await client.get_json("/api/v1/missing")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_429_retry_honours_retry_after_header(respx_mock: respx.MockRouter) -> None:
    _oauth_route(respx_mock)
    route = respx_mock.get(f"{TENANT}/api/v1/throttled").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}, json={}),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    import time

    start = time.monotonic()
    async with SACClient(get_settings()) as client:
        out = await client.get_json("/api/v1/throttled")
    elapsed = time.monotonic() - start

    assert out == {"ok": True}
    assert route.call_count == 2
    # Default exponential backoff has a 0.5s floor; honouring Retry-After: 0
    # means the retry happens almost immediately.
    assert elapsed < 0.4


@pytest.mark.asyncio
async def test_paginate_resolves_service_relative_nextlink(
    respx_mock: respx.MockRouter,
) -> None:
    _oauth_route(respx_mock)

    base = f"{TENANT}/api/v1/dataexport/providers/sac/M1/Data"
    page1 = {
        "value": [{"i": 1}],
        # Service-relative link, as SAC OData commonly emits.
        "@odata.nextLink": "Data?$skiptoken=abc",
    }
    page2 = {"value": [{"i": 2}]}

    respx_mock.get(base, params={"$skiptoken": "abc"}).mock(
        return_value=httpx.Response(200, json=page2)
    )
    respx_mock.get(base).mock(return_value=httpx.Response(200, json=page1))

    async with SACClient(get_settings()) as client:
        out = [
            r
            async for r in client.paginate(
                "/api/v1/dataexport/providers/sac/M1/Data"
            )
        ]
    assert [r["i"] for r in out] == [1, 2]


@pytest.mark.asyncio
async def test_paginate_follows_odata_nextlink(respx_mock: respx.MockRouter) -> None:
    _oauth_route(respx_mock)

    page1 = {
        "value": [{"i": 1}, {"i": 2}],
        "@odata.nextLink": f"{TENANT}/api/v1/x?page=2",
    }
    page2 = {"value": [{"i": 3}]}

    # respx matches in registration order — register the more specific
    # (with-params) route first so the nextLink request hits page2.
    respx_mock.get(f"{TENANT}/api/v1/x", params={"page": "2"}).mock(
        return_value=httpx.Response(200, json=page2)
    )
    respx_mock.get(f"{TENANT}/api/v1/x").mock(return_value=httpx.Response(200, json=page1))

    async with SACClient(get_settings()) as client:
        out = [r async for r in client.paginate("/api/v1/x")]
    assert [r["i"] for r in out] == [1, 2, 3]
