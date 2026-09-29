"""Admin / tenant-info tools."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp import __version__
from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import safe


def register(server: FastMCP, client: SACClient) -> None:
    read = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @server.tool(annotations=read)
    @safe
    async def whoami() -> dict[str, Any]:
        """Identify the OAuth client this server calls SAC with.

        Returns non-secret claims of the current access token (client ID,
        grant type, scopes, subdomain, expiry) — enough to confirm which App
        Integration client and tenant are in use. The token is never returned.
        """

        claims = await client.token_claims()
        expires = claims.get("exp")
        return {
            "client_id": claims.get("client_id") or claims.get("cid") or client.settings.sac_client_id,
            "grant_type": claims.get("grant_type"),
            "scopes": claims.get("scope"),
            "subdomain": claims.get("zdn") or (claims.get("ext_attr") or {}).get("zdn"),
            "zone_id": claims.get("zid"),
            "token_expires_at": (
                datetime.fromtimestamp(float(expires), tz=UTC).isoformat() if expires else None
            ),
            "tenant_url": client.settings.tenant_url_str,
        }

    @server.tool(annotations=read)
    @safe
    async def tenant_info() -> dict[str, Any]:
        """Return the tenant URL, MCP server version, and configured behaviour."""

        settings = client.settings
        return {
            "mcp_version": __version__,
            "tenant_url": settings.tenant_url_str,
            "auth_url": settings.auth_url_str,
            "max_rps": settings.sac_max_rps,
            "response_char_limit": settings.sac_response_char_limit,
        }

    @server.tool(annotations=read)
    @safe
    async def health_check() -> dict[str, Any]:
        """Confirm the tenant is reachable and the OAuth credentials work."""

        await client.get_json("/api/v1/csrf")  # cheapest authenticated GET
        return {"status": "ok"}
