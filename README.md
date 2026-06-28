# SAC-MCP

**Model Context Protocol server for SAP Analytics Cloud**

Connect Claude (or any MCP-compatible LLM client) directly to your SAC tenant. Browse stories, query model data, write back facts and master data, manage users and teams, run content-network jobs, and more — all from natural language.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/protocol-MCP-purple.svg)](https://modelcontextprotocol.io)

---

## Table of contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Tool catalogue](#tool-catalogue)
- [Transports](#transports)
- [Docker](#docker)
- [Agent client](#agent-client)
- [Development](#development)
- [Project layout](#project-layout)

---

## What it does

SAC-MCP exposes the full SAP Analytics Cloud public API surface as MCP tools so an LLM can call them directly.

| Capability | What you can ask Claude to do |
|---|---|
| **Stories & resources** | "List all stories in the Finance folder", "Which models does story X use?" |
| **Model data (read)** | "Show me EMEA revenue for Q1 where margin < 10%" |
| **Model data (write)** | "Import this CSV of actuals into the HR planning model" |
| **Public dimensions** | "List all cost-centre members", "Show the product hierarchy" |
| **Delta / change tracking** | "What rows changed since my last sync?" |
| **Currency & units** | "Upload updated EUR→USD rates effective 2024-01-01" |
| **Users & teams (SCIM)** | "Create a user account for alice@example.com and add her to the Analysts team" |
| **Content Network** | "Export the Finance package and import it to the QA tenant" |
| **Calendar tasks** | "What tasks are pending this week? Mark task 42 as complete" |
| **Multi-actions** | "Trigger the month-end close multi-action" |
| **Audit log** | "What did user bob@example.com change in the last 24 hours?" |
| **Widget data** | "Read the KPI tile values from story XYZ" |
| **Smart query** | "Translate 'top 5 products by sales in EMEA' into an OData call" |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    MCP Client (LLM)                          │
│      Claude Desktop · MCP Inspector · custom client          │
└──────────────────────┬───────────────────────────────────────┘
                       │  stdio  or  Streamable HTTP
                       │          (bearer-auth + CORS)
┌──────────────────────▼───────────────────────────────────────┐
│                    FastMCP server                            │
│  ─────────────────────────────────────────────────────────   │
│   50+ Tools            Resources (sac://…)     Prompts       │
│  ─────────────────────────────────────────────────────────   │
│                    SACClient (single shared)                 │
│   OAuth 2-legged · CSRF cache · retry/backoff                │
│   pagination · token-bucket rate limit                       │
│  ─────────────────────────────────────────────────────────   │
│           Pydantic Settings · structlog (redacted)           │
└──────────────────────┬───────────────────────────────────────┘
                       │  HTTPS
                       ▼
             ┌─────────────────────┐
             │  SAP Analytics      │
             │  Cloud tenant       │
             │  (*.cloud.sap)      │
             └─────────────────────┘
```

**Key design decisions:**

- **One shared HTTP client** — reuses connections (HTTP/2), one OAuth token cache, one CSRF cache, one rate-limit bucket. No race conditions.
- **`x-sap-sac-custom-auth: true`** on every request — tells SAC to skip session-cookie negotiation, avoiding KBA 3387282 / 3566761 failures.
- **`@safe` decorator** on every tool — converts `SACError` into a structured `{"error": ...}` dict the LLM can react to without crashing.
- **`readOnlyHint` / `destructiveHint`** on every tool — MCP clients gate confirmation prompts before any mutation.

---

## Quick start

### Option A — Interactive setup wizard (recommended)

```bash
git clone https://github.com/ltfy4/sac-mcp
cd sac-mcp
uv sync
uv run sac-mcp-setup
```

The wizard asks for your SAC credentials, writes a `.env` file, and prints a ready-to-paste Claude Desktop config snippet.

### Option B — Manual setup

```bash
# 1. Clone & install
git clone https://github.com/ltfy4/sac-mcp
cd sac-mcp
uv sync                        # or: pip install -e .

# 2. Configure credentials
cp .env.example .env
# Edit .env: fill SAC_TENANT_URL, SAC_AUTH_URL, SAC_CLIENT_ID, SAC_CLIENT_SECRET

# 3. Run
uv run sac-mcp
```

### Wire up Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sac": {
      "command": "uv",
      "args": ["--directory", "/path/to/sac-mcp", "run", "sac-mcp"],
      "env": {
        "SAC_TENANT_URL": "https://mycompany.eu10.hcs.cloud.sap",
        "SAC_AUTH_URL":   "https://mycompany.authentication.eu10.hana.ondemand.com",
        "SAC_CLIENT_ID":  "your-client-id",
        "SAC_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

Restart Claude Desktop. You should see SAC tools appear in the tool list.

### Inspect tools interactively

```bash
npx @modelcontextprotocol/inspector uv run sac-mcp
```

---

## Configuration

All settings are environment variables. Copy `.env.example` to `.env` and fill in the values.

### Required

| Variable | Description |
|---|---|
| `SAC_TENANT_URL` | Tenant base URL — e.g. `https://mycompany.eu10.hcs.cloud.sap` |
| `SAC_AUTH_URL` | OAuth authorization server — e.g. `https://mycompany.authentication.eu10.hana.ondemand.com` |
| `SAC_CLIENT_ID` | OAuth client ID (create in SAC: *System → Administration → App Integration*) |
| `SAC_CLIENT_SECRET` | OAuth client secret |

### Optional

| Variable | Default | Description |
|---|---|---|
| `SAC_OAUTH_SCOPE` | _(empty)_ | OAuth scope; leave blank for the default tenant scope |
| `SAC_REQUEST_TIMEOUT` | `60` | HTTP request timeout in seconds |
| `SAC_MAX_RETRIES` | `4` | Retry attempts for transient errors (exponential backoff) |
| `SAC_PAGE_SIZE` | `1000` | Rows per OData page |
| `SAC_MAX_RPS` | `10` | Local rate limit (requests/second); `0` = unlimited |
| `MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `MCP_HTTP_HOST` | `127.0.0.1` | Bind address for HTTP transport |
| `MCP_HTTP_PORT` | `8765` | Port for HTTP transport |
| `MCP_HTTP_BEARER` | _(required for HTTP)_ | Shared bearer token — clients must send `Authorization: Bearer <token>` |
| `MCP_HTTP_CORS_ORIGINS` | _(empty)_ | Comma-separated allowed CORS origins |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | `json` | `json` or `console` |

### Creating the OAuth client in SAC

1. Go to **System → Administration → App Integration**
2. Click **Add a New OAuth Client**
3. Select **Server to Server** (client credentials / 2-legged OAuth)
4. Copy the **Client ID** and **Secret** into your `.env`

The client needs at least the **Analytics** and **Data Export** scopes for read-only use. Add **Data Import** and **SCIM** scopes for write operations.

---

## Tool catalogue

All tools return either:
- `{ "rows": [...], "row_count": N, "next_cursor": "..." }` — for list/query results
- A single object dict — for get/metadata calls
- `{ "error": "...", "code": "...", "status": 4xx }` — on SAC API errors

<details>
<summary><strong>Admin (3 tools)</strong></summary>

| Tool | Type | Description |
|---|---|---|
| `whoami` | read | Identity info for the bound OAuth client |
| `tenant_info` | read | Tenant URL, region, datacenter metadata |
| `health_check` | read | Cheap connectivity check — confirms the server can reach SAC |

</details>

<details>
<summary><strong>Stories (4 tools)</strong></summary>

| Tool | Type | Description |
|---|---|---|
| `list_stories` | read | Stories visible to the OAuth client |
| `get_story` | read | Single story by ID, including referenced models |
| `search_stories` | read | Substring match across story name and description |
| `list_story_models` | read | Models referenced by a story |

</details>

<details>
<summary><strong>Resources / File Repository (2 tools)</strong></summary>

| Tool | Type | Description |
|---|---|---|
| `list_resources` | read | Enumerate `/filerepository/Resources` |
| `get_resource` | read | Fetch a single resource by ID |

</details>

<details>
<summary><strong>Models (4 tools)</strong></summary>

| Tool | Type | Description |
|---|---|---|
| `list_models` | read | Models visible to the OAuth client |
| `get_model_metadata` | read | Full OData `$metadata` document for a model |
| `list_dimensions` | read | Dimensions of a model |
| `list_measures` | read | Measures of a model |

</details>

<details>
<summary><strong>Data Export — fact, master, audit (6 tools)</strong></summary>

Queries the OData v4 Data Export Service (`/api/v1/dataexport/providers/sac/{model_id}/...`).

| Tool | Type | Description |
|---|---|---|
| `read_fact_data` | read | Fact data with `$filter` / `$select` / `$orderby` / `$top` |
| `read_fact_data_delta` | read | Continue a previously initialised delta read |
| `export_fact_data_csv` | read | Same as `read_fact_data` but returns CSV text |
| `read_master_data` | read | Master/dimension members for a model |
| `list_dimension_members` | read | Convenience wrapper around `read_master_data` |
| `read_audit_data` | read | Per-model audit-log entries |

</details>

<details>
<summary><strong>Aggregation — server-side GROUP BY (3 tools)</strong></summary>

Server-side GROUP BY + measure aggregation via the OData v4 `$apply` operator
(`/api/v1/dataexport/providers/sac/{model_id}/Aggregation`). Returns
already-aggregated rows — no client-side aggregation needed. Supported ops:
`sum`, `average`, `min`, `max`, `countdistinct`, `count`.

| Tool | Type | Description |
|---|---|---|
| `read_aggregated_data` | read | Generic GROUP BY with any combination of dimensions and aggregate specs (`{column, op, alias}`) |
| `top_n_by_measure` | read | Top or bottom N dimension members ranked by one aggregated measure |
| `aggregate_by_dimension` | read | One dimension, multiple measures — same aggregation op applied to each |

</details>

<details>
<summary><strong>Data Import — write-back lifecycle (7 tools)</strong></summary>

Manages the full job lifecycle for writing fact or master data back into a model.

| Tool | Type | Description |
|---|---|---|
| `create_import_job` | **write** | Create a fact or master data import job |
| `upload_job_data` | **write** | Append rows or CSV to an open job |
| `validate_job` | **write** | Validate a job (no model mutation) |
| `run_job` | **write** | Execute a validated job (mutates the model) |
| `get_job_status` | read | Poll job state |
| `cancel_job` | **write** | Cancel an in-progress job |
| `list_recent_jobs` | read | Recent jobs for a model |

</details>

<details>
<summary><strong>Public Dimensions (3 tools)</strong></summary>

Tenant-wide shared dimensions (cost centres, products, org hierarchies) via `/api/v1/dataexport/providers/sac_public_dimensions`.

| Tool | Type | Description |
|---|---|---|
| `list_public_dimensions` | read | List all public dimensions on the tenant |
| `read_public_dimension_master_data` | read | Members of one public dimension (filter / select / orderby / top / skip) |
| `read_public_dimension_hierarchies` | read | Members plus hierarchy node references |

</details>

<details>
<summary><strong>Currency & Unit Conversion (9 tools)</strong></summary>

Tenant-level currency and unit-of-measure tables, plus per-model currency data.

| Tool | Type | Description |
|---|---|---|
| `list_currency_tables` | read | List currency conversion tables |
| `get_currency_table` | read | One currency table's metadata |
| `get_currency_rates` | read | Exchange rates in a table |
| `upload_currency_rates` | **write** | Upload rates (sourceCurrency / targetCurrency / rateType / validFrom / rate) |
| `list_unit_tables` | read | List unit-of-measure tables |
| `get_unit_table` | read | One unit table's metadata |
| `get_unit_rates` | read | Unit conversion factors |
| `upload_unit_rates` | **write** | Upload unit conversion factors |
| `read_currency_data` | read | Per-model `CurrencyData` OData entity |

</details>

<details>
<summary><strong>Delta / Change Tracking (2 tools)</strong></summary>

Uses OData v4 delta semantics (`Prefer: odata.track-changes` + `$deltatoken`) to fetch only rows that changed since a baseline call.

| Tool | Type | Description |
|---|---|---|
| `init_delta_tracking` | read | Establish a baseline read; returns rows + a `delta_token` |
| `get_delta_changes` | read | Rows changed since the previous `delta_token` |

</details>

<details>
<summary><strong>Widget Query (2 tools)</strong></summary>

Programmatic access to widget data inside SAC stories. Currently only `kpiTile` widget types are supported by the public Widget Query API.

| Tool | Type | Description |
|---|---|---|
| `get_widget_data` | read | Rendered values from a story widget (kpiTile only) |
| `list_story_widgets` | read | Widget descriptors embedded in a story |

</details>

<details>
<summary><strong>Users — SCIM (3 tools)</strong></summary>

| Tool | Type | Description |
|---|---|---|
| `list_users` | read | List SCIM users |
| `create_user` | **write** | Create a new SCIM user |
| `deactivate_user` | **write** | Deactivate a SCIM user |

</details>

<details>
<summary><strong>Teams — SCIM Groups (3 tools)</strong></summary>

| Tool | Type | Description |
|---|---|---|
| `list_teams` | read | List SCIM groups |
| `add_member` | **write** | Add a user to a team |
| `remove_member` | **write** | Remove a user from a team |

</details>

<details>
<summary><strong>Content Network (4 tools)</strong></summary>

| Tool | Type | Description |
|---|---|---|
| `list_packages` | read | Available content-network packages |
| `create_cn_import_job` | **write** | Start a content-network import |
| `create_cn_export_job` | **write** | Start a content-network export |
| `get_cn_job_status` | read | Poll a content-network job |

</details>

<details>
<summary><strong>Calendar Tasks (2 tools)</strong></summary>

| Tool | Type | Description |
|---|---|---|
| `list_calendar_tasks` | read | Tasks visible to the OAuth client |
| `update_task_status` | **write** | Mutate a task's status |

</details>

<details>
<summary><strong>Multi-Action (2 tools)</strong></summary>

| Tool | Type | Description |
|---|---|---|
| `list_multi_actions` | read | List defined multi-actions |
| `run_multi_action` | **write** | Trigger a multi-action run |

</details>

<details>
<summary><strong>Audit Log (2 tools)</strong></summary>

| Tool | Type | Description |
|---|---|---|
| `query_audit_log` | read | Raw OData passthrough against `/api/v1/auditing/AuditLog` |
| `recent_changes_for_user` | read | Audit entries for a specific user since an ISO timestamp |

</details>

<details>
<summary><strong>Model Monitoring (3 tools)</strong></summary>

Answers "is my data fresh", "when did this model last load", "how big is this model" via `/api/v1/monitoring/models/...`.

| Tool | Type | Description |
|---|---|---|
| `list_monitored_models` | read | All models with monitoring metadata (size, rowCount, lastImportTime, lastModifiedBy, lastModifiedTime) |
| `get_model_monitoring` | read | Monitoring detail for a single model |
| `get_model_job_history` | read | Recent import/refresh jobs for a model, optionally filtered by start time |

</details>

<details>
<summary><strong>Query routing (2 tools)</strong></summary>

| Tool | Type | Description |
|---|---|---|
| `sql_query` | read | Accepts a SQL-like query string; routes automatically. Queries with explicit aggregate functions (`SUM(col)`, `COUNT(col)`, etc.) go to the Aggregation entity for server-side GROUP BY. With `story_id` + `widget_id` the Widget Query API is preferred instead. Everything else uses OData. |
| `smart_query` | read | **Plan-only NL→OData/Aggregation translator.** Takes a natural-language question, reads `$metadata`, and returns a query plan + rationale. When aggregation intent is detected (`sum` / `total` / `average` / `count`) the plan targets `read_aggregated_data` (`next_tool="read_aggregated_data"`); otherwise it targets `read_fact_data`. Never executes the query — the caller reviews and runs it explicitly. |

</details>

---

## Transports

### stdio (default) — for local clients

```bash
uv run sac-mcp
```

Used by Claude Desktop, the MCP Inspector, and any other local MCP client running on the same machine. The process communicates over stdin/stdout; logs go to stderr.

### Streamable HTTP — for hosted / team use

```bash
MCP_TRANSPORT=http \
MCP_HTTP_BEARER=$(openssl rand -hex 32) \
MCP_HTTP_HOST=0.0.0.0 \
MCP_HTTP_PORT=8765 \
uv run sac-mcp
```

Clients must send `Authorization: Bearer <token>`. Optionally restrict origins with `MCP_HTTP_CORS_ORIGINS`.

| | stdio | Streamable HTTP |
|---|---|---|
| Client location | Same machine | Any network client |
| Transport auth | OS process isolation | Bearer token |
| CORS | N/A | Configurable |
| Multi-session | No | Yes |
| Typical use | Dev workstation | Hosted server, team gateway |

---

## Docker

A minimal production image is included:

```bash
# Build
docker build -t sac-mcp .

# Run
docker run -p 8765:8765 \
  -e SAC_TENANT_URL=https://mycompany.eu10.hcs.cloud.sap \
  -e SAC_AUTH_URL=https://mycompany.authentication.eu10.hana.ondemand.com \
  -e SAC_CLIENT_ID=your-client-id \
  -e SAC_CLIENT_SECRET=your-client-secret \
  -e MCP_HTTP_BEARER=your-random-secret \
  sac-mcp
```

The image defaults to `MCP_TRANSPORT=http` on port `8765`, bound to `0.0.0.0`, running as a non-root user (`sacmcp`, uid 1001).

---

## Agent client

[`agent_client/`](agent_client/) is a minimal interactive harness that connects to the running SAC-MCP server over stdio and lets an LLM (Anthropic Claude or OpenAI) call your SAC tenant end-to-end.

```bash
cd agent_client
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...
python agent.py
```

```
Connected! 50 tools available.

You: What models are available on this tenant?
Assistant: [Calling list_models] There are 3 models: BestRunJuice_SampleModel, HR_Planning_2024, Finance_Actuals.

You: Show me EMEA revenue for Q1 where margin < 10%
Assistant: [Calling smart_query → read_fact_data] Here are the results (12 rows)...

You: quit
```

Useful for smoke tests and demos. Not intended for production deployment.

---

## Development

### Install with dev dependencies

```bash
uv sync --extra dev
# or: pip install -e ".[dev]"
```

### Common commands

```bash
# Unit tests (offline, all HTTP mocked with respx)
uv run pytest tests/unit -q

# Single test
uv run pytest tests/unit/test_http_client.py::test_csrf_refresh_on_403 -v

# Lint
uv run ruff check sac_mcp tests

# Type check
uv run mypy sac_mcp

# Interactive MCP inspector
npx @modelcontextprotocol/inspector uv run sac-mcp

# Live integration tests (requires real tenant credentials in .env)
SAC_LIVE_TEST=1 uv run pytest tests/integration -q -m live
```

### Adding a tool to an existing surface

1. Open `sac_mcp/tools/<surface>.py` (e.g. `dataexport.py`).
2. Inside the `register(server, client)` function, add:

```python
@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
@safe
async def my_new_tool(model_id: str, top: int = 100) -> dict[str, Any]:
    """One-line summary shown to the LLM. Args: model_id: the model to query."""
    rows: list[dict[str, Any]] = []
    async for r in client.paginate(
        f"/api/v1/dataexport/providers/sac/{model_id}/Whatever",
        params=ODataQuery(top=top).to_params(),
        max_rows=top,
    ):
        rows.append(r)
    return page_envelope(compact(rows))
```

3. Add a unit test in `tests/unit/test_<surface>.py` using `respx_mock`.
4. Run `pytest tests/unit -q` — must be green before committing.

### Adding a new SAC surface

1. Create `sac_mcp/tools/<surface>.py` with a `register(server, client)` function. Copy `audit.py` as a minimal template.
2. Import and call `<surface>.register(server, client)` from `sac_mcp/server.py`.
3. Add tools, tests, and update this README's tool catalogue.

### Definition of done

- [ ] `pytest tests/unit -q` is green
- [ ] `ruff check sac_mcp tests` is clean
- [ ] `mypy sac_mcp` is clean
- [ ] Tool count / hint assertions in `test_server_assembly.py` still pass
- [ ] Tool catalogue above updated for any new user-facing tools
- [ ] Commit message explains *why*, not *what*
- [ ] Pushed to a feature branch — never directly to `main`

---

## Project layout

```
sac_mcp/
├── server.py            # build_server(): registers all tools, resources, prompts
├── __main__.py          # entry point; reads MCP_TRANSPORT and dispatches
├── config.py            # Pydantic Settings; get_settings() is lru_cached
├── logging.py           # structlog + secret redaction
├── client/
│   ├── auth.py          # OAuthTokenProvider (2-legged, asyncio.Lock, 60 s leeway)
│   ├── csrf.py          # CsrfTokenCache; refresh on 403
│   ├── http.py          # SACClient: request, get_json, post_json, paginate
│   ├── odata.py         # ODataQuery builder (eq, contains, and_, or_, …)
│   ├── errors.py        # SACError + from_response() — normalises 3 SAC error envelopes
│   ├── ratelimit.py     # async TokenBucket
│   └── models.py        # permissive Pydantic DTOs (SACEntity, …)
├── tools/               # one file per SAC surface
│   ├── _common.py       # safe(), compact(), as_csv(), page_envelope()
│   ├── admin.py
│   ├── stories.py
│   ├── resources.py
│   ├── models.py
│   ├── dataexport.py
│   ├── dataimport.py
│   ├── public_dimensions.py
│   ├── currency.py
│   ├── difference.py
│   ├── widget_query.py
│   ├── users.py
│   ├── teams.py
│   ├── content_network.py
│   ├── calendar.py
│   ├── multiaction.py
│   ├── audit.py
│   ├── sql_query.py
│   └── smart_query.py
├── resources/           # MCP resources (read-only URIs)
│   ├── tenant.py        # sac://tenant/info
│   └── catalog.py       # sac://catalog/models (5-min cache)
├── prompts/             # MCP prompts
│   ├── explore_tenant.py
│   ├── plan_writeback.py
│   └── audit_drilldown.py
└── transports/
    ├── stdio.py
    └── http.py          # bearer-auth + optional CORS

tests/
├── conftest.py          # respx fixtures, auto-loaded env (SAC_MAX_RPS=0)
└── unit/                # 60 tests; no live network
```

Additional docs in [`docs/`](docs/):
- [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) — detailed design rationale (auth flow, retry strategy, pagination model)
- [`CONVENTIONS.md`](docs/CONVENTIONS.md) — coding conventions for contributors
- [`SAC_API_NOTES.md`](docs/SAC_API_NOTES.md) — SAC-specific API quirks and known issues
- [`tools.md`](docs/tools.md) — machine-readable tool catalogue

---

## License

MIT — see [LICENSE](LICENSE) for details.
