"""Admin / tenant-info tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import safe


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def whoami() -> dict[str, Any]:
        """Return the OAuth client identity that the MCP server is using.

        Useful as a connectivity / credentials sanity check before calling other
        tools.
        """

        # /api/v1/scim/Me returns the principal of the calling token.
        try:
            return await client.get_json("/api/v1/scim/Me")
        except Exception:  # fall back to a vanilla model list call
            return {"note": "scim/Me not available; fell back to listing 1 model",
                    "models": await client.get_json(
                        "/api/v1/dataexport/administration/Namespaces('sac')/Providers",
                        params={"$top": 1},
                    )}

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def tenant_info() -> dict[str, Any]:
        """Return the tenant URL, MCP server version, and configured behaviour."""

        from sac_mcp import __version__
        settings = client._settings
        return {
            "mcp_version": __version__,
            "tenant_url": settings.tenant_url_str,
            "auth_url": settings.auth_url_str,
            "page_size": settings.sac_page_size,
            "max_rps": settings.sac_max_rps,
        }

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def health_check() -> dict[str, Any]:
        """Make a cheap GET against SAC to confirm reachability and auth."""

        await client.get_json("/api/v1/csrf")  # any GET will do
        return {"status": "ok"}
