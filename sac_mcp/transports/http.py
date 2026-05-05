"""Streamable HTTP transport entry point.

Wraps the FastMCP Streamable HTTP app with:

* Bearer-token authentication (``MCP_HTTP_BEARER``) — protects the MCP endpoint
  itself; the SAC OAuth client credentials are still set via env on the server.
* Optional CORS allowlist.
"""

from __future__ import annotations

import secrets

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount

from sac_mcp.config import Settings
from sac_mcp.logging import get_logger

_log = get_logger(__name__)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Starlette, expected_token: str) -> None:
        super().__init__(app)
        self._expected = expected_token

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Allow CORS preflight without a token.
        if request.method == "OPTIONS":
            return await call_next(request)

        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return JSONResponse({"error": "missing bearer token"}, status_code=401)
        if not secrets.compare_digest(token, self._expected):
            return JSONResponse({"error": "invalid bearer token"}, status_code=403)
        return await call_next(request)


def run_http(server: FastMCP, settings: Settings) -> None:
    if settings.mcp_http_bearer is None:
        raise SystemExit(
            "MCP_HTTP_BEARER must be set when MCP_TRANSPORT=http (used to "
            "authenticate clients connecting to this MCP endpoint)."
        )

    expected = settings.mcp_http_bearer.get_secret_value()

    middleware = [
        Middleware(BearerAuthMiddleware, expected_token=expected),
    ]
    if settings.cors_origins_list:
        middleware.append(
            Middleware(
                CORSMiddleware,
                allow_origins=settings.cors_origins_list,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["Authorization", "Content-Type"],
            )
        )

    # FastMCP exposes a Starlette ASGI app for streamable HTTP.
    mcp_app = server.streamable_http_app()

    app = Starlette(
        routes=[Mount("/", app=mcp_app)],
        middleware=middleware,
    )

    _log.info(
        "http.start",
        host=settings.mcp_http_host,
        port=settings.mcp_http_port,
        cors=settings.cors_origins_list,
    )
    uvicorn.run(
        app,
        host=settings.mcp_http_host,
        port=settings.mcp_http_port,
        log_level=settings.log_level.lower(),
    )
