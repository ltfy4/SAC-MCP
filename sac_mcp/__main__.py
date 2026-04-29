"""Entry point: `python -m sac_mcp` or `sac-mcp`."""

from __future__ import annotations

from sac_mcp.config import get_settings
from sac_mcp.logging import configure_logging
from sac_mcp.server import build_server


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    server = build_server(settings)

    if settings.mcp_transport == "stdio":
        from sac_mcp.transports.stdio import run_stdio

        run_stdio(server)
    elif settings.mcp_transport == "http":
        from sac_mcp.transports.http import run_http

        run_http(server, settings)
    else:
        raise SystemExit(f"Unknown MCP_TRANSPORT: {settings.mcp_transport!r}")


if __name__ == "__main__":
    main()
