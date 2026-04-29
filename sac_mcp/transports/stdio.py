"""stdio transport entry point."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def run_stdio(server: FastMCP) -> None:
    server.run(transport="stdio")
