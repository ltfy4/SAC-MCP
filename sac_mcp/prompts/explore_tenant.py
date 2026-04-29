"""Prompt: walk the user through SAC tenant discovery."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from sac_mcp.client.http import SACClient


def register(server: FastMCP, _client: SACClient) -> None:
    @server.prompt()
    def explore_tenant() -> str:
        """Guide the LLM to discover stories → models → data step by step."""

        return (
            "You are connected to a SAP Analytics Cloud tenant via the sac-mcp "
            "MCP server. To explore it efficiently:\n\n"
            "1. Call `tenant_info` to confirm what tenant you're talking to.\n"
            "2. Call `list_models` (or read the `sac://catalog/models` resource) "
            "to enumerate available models.\n"
            "3. Call `list_stories` to see analytic stories — each story lists "
            "the models it depends on.\n"
            "4. For a model of interest, call `get_model_metadata` to learn its "
            "dimensions and measures.\n"
            "5. Use `read_master_data` to understand dimension members before "
            "building filters.\n"
            "6. Use `read_fact_data` with an OData `$filter` to query actual "
            "data; prefer `$top` ≤ 100 to keep responses small.\n\n"
            "Tools whose names start with `create_`, `update_`, `run_`, "
            "`deactivate_` mutate the tenant — confirm with the user first."
        )
