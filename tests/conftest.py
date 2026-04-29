"""Shared test fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
import respx

from sac_mcp.client.auth import OAuthTokenProvider
from sac_mcp.client.http import SACClient
from sac_mcp.config import Settings


TENANT = "https://tenant.example.com"
AUTH = "https://auth.example.com"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAC_TENANT_URL", TENANT)
    monkeypatch.setenv("SAC_AUTH_URL", AUTH)
    monkeypatch.setenv("SAC_CLIENT_ID", "cid")
    monkeypatch.setenv("SAC_CLIENT_SECRET", "sec")
    monkeypatch.setenv("SAC_MAX_RPS", "0")  # disable rate limit in tests
    # Re-evaluate cached settings.
    from sac_mcp.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    from sac_mcp.config import get_settings

    return get_settings()


@pytest_asyncio.fixture
async def mock_oauth(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.post(f"{AUTH}/oauth/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "tok", "expires_in": 3600}
        )
    )


@pytest_asyncio.fixture
async def client(
    settings: Settings,
    respx_mock: respx.MockRouter,
    mock_oauth: respx.Route,
) -> AsyncIterator[SACClient]:
    sc = SACClient(settings)
    try:
        yield sc
    finally:
        await sc.aclose()
