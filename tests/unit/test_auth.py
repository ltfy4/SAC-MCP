"""OAuth token provider tests."""

from __future__ import annotations

import httpx
import pytest
import respx

from sac_mcp.client.auth import OAuthTokenProvider
from sac_mcp.client.errors import SACError
from sac_mcp.config import get_settings

AUTH = "https://auth.example.com"


@pytest.mark.asyncio
async def test_token_is_fetched_and_cached(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.post(f"{AUTH}/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})
    )
    settings = get_settings()
    provider = OAuthTokenProvider(settings)

    t1 = await provider.get_token()
    t2 = await provider.get_token()

    assert t1 == "abc"
    assert t2 == "abc"
    assert route.call_count == 1  # cached on second call


@pytest.mark.asyncio
async def test_invalidate_forces_refresh(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.post(f"{AUTH}/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "x", "expires_in": 3600})
    )
    settings = get_settings()
    provider = OAuthTokenProvider(settings)

    await provider.get_token()
    await provider.invalidate()
    await provider.get_token()

    assert route.call_count == 2


@pytest.mark.asyncio
async def test_token_endpoint_failure_propagates(respx_mock: respx.MockRouter) -> None:
    respx_mock.post(f"{AUTH}/oauth/token").mock(
        return_value=httpx.Response(401, json={"error": "invalid_client"})
    )
    provider = OAuthTokenProvider(get_settings())
    with pytest.raises(SACError):
        await provider.get_token()
