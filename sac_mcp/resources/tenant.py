"""``sac://tenant/info`` resource."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from sac_mcp import __version__
from sac_mcp.client.http import SACClient


def register(server: FastMCP, client: SACClient) -> None:
    @server.resource("sac://tenant/info", mime_type="application/json")
    def tenant_info() -> str:
        s = client._settings
        return json.dumps(
            {
                "mcp_version": __version__,
                "tenant_url": s.tenant_url_str,
                "auth_url": s.auth_url_str,
                "max_rps": s.sac_max_rps,
                "page_size": s.sac_page_size,
            },
            indent=2,
        )
