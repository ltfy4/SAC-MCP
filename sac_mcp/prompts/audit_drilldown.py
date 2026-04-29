"""Prompt: turn natural-language audit questions into OData filters."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from sac_mcp.client.http import SACClient


def register(server: FastMCP, _client: SACClient) -> None:
    @server.prompt()
    def audit_drilldown(question: str) -> str:
        """Help the LLM build a precise audit query from a natural question."""

        return (
            "Convert the user's question below into one or more `query_audit_log` "
            "calls. Build OData `$filter` expressions using fields like `Action`, "
            "`UserName`, `Timestamp` (ISO-8601), `EntityType`, `EntityId`. Default "
            "`$orderby` is `Timestamp desc`. Keep `top` ≤ 200 unless the user "
            "explicitly asks for more.\n\n"
            f"User question: {question}"
        )
