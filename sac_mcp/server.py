"""FastMCP server factory.

The single :func:`build_server` function returns a configured
:class:`~mcp.server.fastmcp.FastMCP` instance with every tool, resource and
prompt registered. Both transports (stdio, streamable-http) consume the same
server.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from sac_mcp.client.http import SACClient
from sac_mcp.config import Settings


def build_server(settings: Settings) -> FastMCP:
    """Construct the FastMCP app with all tools/resources/prompts registered."""

    allowed = settings.allowed_hosts_list
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(allowed),
        allowed_hosts=allowed,
    )

    server = FastMCP(
        name="sac-mcp",
        instructions=(
            "SAP Analytics Cloud MCP server. Use these tools to browse the SAC "
            "tenant (stories, models, resources), query model data via the OData "
            "Data Export Service, write back facts/master data via the Data "
            "Import job lifecycle, manage users/teams (SCIM), and orchestrate "
            "Content Network, Calendar Tasks, Data Action and Multi-Action "
            "runs. Read tools are safe; tools that mutate the tenant are "
            "marked destructive."
        ),
        transport_security=transport_security,
    )

    # Single shared client for the lifetime of the server process. Modules that
    # need it receive it explicitly via their ``register(server, client)`` hook.
    client = SACClient(settings)

    from sac_mcp.prompts import audit_drilldown, explore_tenant, plan_writeback
    from sac_mcp.resources import catalog, tenant
    from sac_mcp.tools import (
        admin,
        aggregation,
        audit,
        calendar,
        content_network,
        currency,
        dataactions,
        dataexport,
        dataimport,
        difference,
        models,
        monitoring,
        multiaction,
        public_dimensions,
        smart_query,
        sql_query,
        stories,
        teams,
        users,
        widget_query,
    )
    from sac_mcp.tools import (
        resources as resources_tools,
    )

    for module in (
        admin, aggregation, audit, calendar, content_network, dataactions,
        dataexport, public_dimensions, difference, widget_query, smart_query,
        sql_query, dataimport, currency, models, monitoring, multiaction, resources_tools,
        stories, teams, users, catalog, tenant, audit_drilldown, explore_tenant,
        plan_writeback,
    ):
        module.register(server, client)

    return server
