# SAC-MCP — SAP Analytics Cloud MCP Server

A Model Context Protocol (MCP) server that exposes the full SAP Analytics Cloud (SAC) public API surface as MCP tools, resources, and prompts. Drop it into Claude Desktop, Claude Code, or any MCP-compatible client and let an LLM browse stories, query model data, write back facts/master data, manage users, and orchestrate Content Network jobs.

## Features

- **Comprehensive coverage** of SAC public APIs:
  - Public REST: stories, file repository / resources, SCIM users & teams, calendar tasks, multi-actions, admin
  - Data Export Service (OData v4): fact / master / audit data
  - Data Import Service: job lifecycle (create, upload, validate, run, status, cancel)
  - Content Network: package import / export jobs
- **2-legged OAuth** (client credentials) with token caching and proactive refresh
- **CSRF token** auto-fetch for write operations, with retry on 403
- **Two transports**: `stdio` for local clients (Claude Desktop) and **Streamable HTTP** for remote/hosted use
- **LLM-friendly output**: large tables are returned as compact JSON, markdown, or as MCP resources
- **Read-only & destructive hints** so MCP clients can confirm before mutating writes
- **Pagination, retry, rate-limit** baked into the HTTP client

## Quick start

### Quick setup

Run the interactive setup wizard after installation:

```bash
uv run sac-mcp-setup
```

It prompts for your SAC credentials, writes a `.env` file, and prints a ready-to-paste Claude Desktop config snippet. See below for manual configuration if you prefer.

### Manual configuration

```bash
# 1. Clone & install (uv recommended)
uv sync

# 2. Configure
cp .env.example .env
# Fill SAC_TENANT_URL, SAC_AUTH_URL, SAC_CLIENT_ID, SAC_CLIENT_SECRET

# 3. Run (stdio)
uv run sac-mcp

# Or run as Streamable HTTP server
MCP_TRANSPORT=http MCP_HTTP_BEARER=<random-secret> uv run sac-mcp
```

### Wire up in Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sac": {
      "command": "uv",
      "args": ["--directory", "/path/to/SAC-MCP", "run", "sac-mcp"],
      "env": {
        "SAC_TENANT_URL": "https://mycompany.eu10.hcs.cloud.sap",
        "SAC_AUTH_URL": "https://mycompany.authentication.eu10.hana.ondemand.com",
        "SAC_CLIENT_ID": "...",
        "SAC_CLIENT_SECRET": "..."
      }
    }
  }
}
```

### Inspect with the MCP Inspector

```bash
npx @modelcontextprotocol/inspector uv run sac-mcp
```

## Configuration

All configuration is via environment variables (see `.env.example`). Required:

| Variable | Description |
|---|---|
| `SAC_TENANT_URL` | Tenant base URL, e.g. `https://mycompany.eu10.hcs.cloud.sap` |
| `SAC_AUTH_URL` | OAuth authorization server URL |
| `SAC_CLIENT_ID` / `SAC_CLIENT_SECRET` | Created in SAC under *System → Administration → App Integration* (2-legged client) |

## Tool catalogue

See [`docs/tools.md`](docs/tools.md) for the full list. Highlights:

- `list_models`, `get_model_metadata`, `list_dimensions`, `list_measures`
- `read_fact_data`, `read_master_data`, `read_audit_data` (OData filter / top / select / orderby)
- `list_stories`, `search_stories`, `list_resources`, `find_by_type`
- `create_import_job`, `upload_job_data`, `validate_job`, `run_job`, `get_job_status`
- `list_users`, `create_user`, `add_team_member`
- `create_cn_import_job`, `create_cn_export_job`
- `list_calendar_tasks`, `update_task_status`
- `run_multi_action`
- `list_public_dimensions`, `read_public_dimension_master_data`, `read_public_dimension_hierarchies`
- `list_currency_tables`, `get_currency_rates`, `upload_currency_rates`
- `list_unit_tables`, `get_unit_rates`, `upload_unit_rates`, `read_currency_data`
- `init_delta_tracking`, `get_delta_changes` (OData v4 change tracking)
- `get_widget_data`, `list_story_widgets`
- `smart_query` — automatic OData / Widget Query routing for SQL-like queries

## Bundled agent client

A minimal interactive harness that connects to the running SAC-MCP server
over stdio and lets an LLM (Anthropic Claude or OpenAI) call your SAC tenant
end-to-end lives in [`agent_client/`](agent_client/README.md). Useful for
smoke tests and demos; not meant for production deployment.

## Development

```bash
uv sync --extra dev
uv run pytest tests/unit -q
uv run ruff check
uv run mypy sac_mcp
```

Live integration tests (requires real tenant credentials in `.env`):

```bash
SAC_LIVE_TEST=1 uv run pytest tests/integration -q -m live
```

## License

MIT
