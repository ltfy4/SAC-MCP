# SAC-MCP

**A Model Context Protocol server for SAP Analytics Cloud.**

Expose the full SAC public API surface — stories, model data, write-back, users, content network, calendar, audit, monitoring — to any MCP-compatible LLM client. Query in natural language. Hit the same OData and REST endpoints SAC's own clients use, with OAuth, CSRF, retry, pagination and rate limiting handled for you.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/protocol-MCP-purple.svg)](https://modelcontextprotocol.io)

---

## Table of contents

- [Highlights](#highlights)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Tool catalogue](#tool-catalogue)
- [Transports](#transports)
- [Troubleshooting](#troubleshooting)
- [Docker](#docker)
- [Agent client](#agent-client)
- [Development](#development)
- [Project layout](#project-layout)
- [Documentation](#documentation)
- [License](#license)

---

## Highlights

50+ tools across 20 SAC surfaces — every one of them async, typed, and gated by an MCP `readOnlyHint` / `destructiveHint` so clients can decide whether to confirm.

| Area | What you can ask the LLM to do |
|---|---|
| **Stories & resources** | "List all stories in the Finance folder", "Which models does story X use?" |
| **Model data (read)** | "Show me EMEA revenue for Q1 where margin < 10%" |
| **Aggregation (server-side)** | "Top 5 regions by total sales", "Sum amount grouped by year and country" |
| **Model data (write)** | "Import this CSV of actuals into the HR planning model" |
| **Public dimensions** | "List all cost-centre members", "Show the product hierarchy" |
| **Delta / change tracking** | "What rows changed since my last sync?" |
| **Currency & units** | "Upload updated EUR→USD rates effective 2024-01-01" |
| **Users & teams (SCIM)** | "Create a user for alice@example.com and add her to the Analysts team" |
| **Content Network** | "Export the Finance package and import it to the QA tenant" |
| **Calendar tasks** | "What tasks are pending this week? Mark task 42 as complete" |
| **Multi-actions** | "Trigger the month-end close multi-action" |
| **Audit log** | "What did bob@example.com change in the last 24 hours?" |
| **Monitoring** | "Which models haven't loaded in the last week?", "Show job history for model X" |
| **Widget data** | "Read the KPI tile values from story XYZ" |
| **Smart / SQL routing** | "Translate 'top 5 products by sales in EMEA' into an OData call" |

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

### Key design decisions

- **One shared HTTP client** — reuses connections (HTTP/2), one OAuth token cache, one CSRF cache, one rate-limit bucket. No race conditions.
- **`x-sap-sac-custom-auth: true`** on every request — tells SAC to skip session-cookie negotiation, avoiding the well-known KBA 3387282 / 3566761 failure mode.
- **`@safe` decorator on every tool** — converts `SACError` into a structured `{"error": ...}` dict so the LLM can react instead of crashing.
- **`readOnlyHint` / `destructiveHint` on every tool** — clients gate confirmation prompts before any mutation.
- **Plan-only NL→OData translation** — the natural-language `smart_query` tool returns a query *plan*, never executes it; the caller reviews and runs the suggested call explicitly. That confirmation step is the safety boundary.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design rationale.

---

## Quick start

### Option A — Interactive setup wizard (recommended)

```bash
git clone https://github.com/ltfy4/sac-mcp
cd sac-mcp
uv sync
uv run sac-mcp-setup
```

The wizard asks for your SAC credentials, writes a `.env` file, and prints a ready-to-paste MCP client config snippet.

### Option B — Manual setup

```bash
git clone https://github.com/ltfy4/sac-mcp
cd sac-mcp
uv sync                                # or: pip install -e .
cp .env.example .env                   # then edit SAC_* values
uv run sac-mcp                         # stdio transport (default)
```

### Wire up an MCP client (Claude Desktop example)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or the equivalent on your platform:

```json
{
  "mcpServers": {
    "sac": {
      "command": "uv",
      "args": ["--directory", "/path/to/sac-mcp", "run", "sac-mcp"],
      "env": {
        "SAC_TENANT_URL":    "https://mycompany.eu10.hcs.cloud.sap",
        "SAC_AUTH_URL":      "https://mycompany.authentication.eu10.hana.ondemand.com",
        "SAC_CLIENT_ID":     "your-client-id",
        "SAC_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

Restart the client. SAC tools should appear in the tool list.

### Inspect tools interactively

```bash
npx @modelcontextprotocol/inspector uv run sac-mcp
```

---

## Configuration

All settings are environment variables. Copy `.env.example` to `.env` and fill the values.

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
| `MCP_HTTP_BEARER` | _(required for HTTP)_ | Shared bearer token — generate with `openssl rand -hex 32` |
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

All tools return one of:

- `{ "rows": [...], "row_count": N, "next_cursor": "..." }` for collection results
- A single object dict for `get_*` / metadata calls
- `{ "error": "...", "code": "...", "status": 4xx }` on SAC errors

| Surface | Tools | Type mix | Summary |
|---|---:|---|---|
| **Admin** | 3 | read | Identity, tenant metadata, health check |
| **Stories** | 4 | read | List, search, fetch story → models |
| **Resources (file repo)** | 2 | read | `/filerepository/Resources` enumeration |
| **Models** | 4 | read | List models, metadata, dimensions, measures |
| **Data Export** | 6 | read | Fact / master / audit OData reads (+ delta + CSV) |
| **Aggregation** | 3 | read | Server-side GROUP BY via OData `$apply` |
| **Data Import** | 7 | read + write | Job lifecycle: create → upload → validate → run → status → cancel |
| **Public Dimensions** | 3 | read | Tenant-wide shared dimensions (cost centres, products, hierarchies) |
| **Currency & Units** | 9 | read + write | Conversion tables, rates, per-model currency data |
| **Delta tracking** | 2 | read | OData v4 delta token reads |
| **Widget Query** | 2 | read | Story widget data (`kpiTile`) |
| **Users (SCIM)** | 3 | read + write | List / create / deactivate |
| **Teams (SCIM Groups)** | 3 | read + write | List / add member / remove member |
| **Content Network** | 4 | read + write | Packages, import / export jobs |
| **Calendar Tasks** | 2 | read + write | List tasks, update status |
| **Multi-Action** | 2 | read + write | List, trigger |
| **Audit Log** | 2 | read | Tenant audit queries (OData passthrough + user-scoped helper) |
| **Monitoring** | 3 | read | Model freshness, row counts, job history |
| **Query routing** | 2 | read | `sql_query` (SQL-like router) and `smart_query` (plan-only NL→OData translator) |

**[Full per-tool reference → `docs/tools.md`](docs/tools.md)**

Every write tool is marked `destructiveHint=True` in its annotation so MCP clients prompt for confirmation by default.

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

Clients must send `Authorization: Bearer <token>`. Optionally restrict origins with `MCP_HTTP_CORS_ORIGINS`. The server does **not** terminate TLS — put it behind nginx, Caddy, or a cloud load balancer for production.

| | stdio | Streamable HTTP |
|---|---|---|
| Client location | Same machine | Any network client |
| Transport auth | OS process isolation | Bearer token |
| CORS | N/A | Configurable |
| Multi-session | No | Yes |
| Typical use | Dev workstation | Hosted server, team gateway |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` on every call | OAuth client credentials wrong, or `SAC_AUTH_URL` doesn't match the tenant region | Re-check `SAC_CLIENT_ID` / `SAC_CLIENT_SECRET` and confirm `SAC_AUTH_URL` matches your tenant's data centre (`eu10`, `us10`, etc.). The setup wizard derives the auth URL from the tenant URL — re-run it if unsure. |
| `403` on writes only, reads work fine | OAuth client missing the **Data Import** or **SCIM** scope | Add the scope in SAC (*App Integration*) and refresh credentials. |
| Repeating `403 missing CSRF token` | CSRF cache is stale and refresh isn't being attempted | `SACClient` already invalidates and retries once on CSRF 403. If you see it loop, file an issue with the failing path and headers. |
| `Connection error` only on writes | Outbound network blocking SAC's OAuth or CSRF endpoints | Verify the host can reach both `SAC_TENANT_URL` and `SAC_AUTH_URL` — they are often on different sub-domains. |
| Server starts but no tools show in the client | MCP client connected to the wrong command or `.env` is empty | Check the client's connection log. For stdio, the command must be the *exact* one that works in your shell. Logs go to stderr — capture and read them. |
| `429 Too Many Requests` from SAC | Local rate limit too high for your tenant's quota | Lower `SAC_MAX_RPS` (e.g. `5`) or run the server with fewer concurrent agents. |
| Streamable HTTP returns `401` to your client | Wrong bearer token or no `Authorization` header | Make sure the client sends `Authorization: Bearer <token>` and the token matches `MCP_HTTP_BEARER` byte-for-byte (no surrounding whitespace). |
| `pytest` fails locally but passes in CI | Stale virtualenv | Re-install: `uv sync --extra dev` or `pip install -e ".[dev]"`. |

Still stuck? Open an issue with: SAC region (`eu10` / `us10` / …), transport (`stdio` / `http`), the exact error message, and a redacted log snippet.

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
  -e MCP_HTTP_BEARER=$(openssl rand -hex 32) \
  sac-mcp
```

The image defaults to `MCP_TRANSPORT=http` on port `8765`, bound to `0.0.0.0`, running as a non-root user (`sacmcp`, uid 1001).

---

## Agent client

[`agent_client/`](agent_client/) is a minimal interactive harness that connects to the running SAC-MCP server over stdio and lets an LLM (Anthropic or OpenAI) call the SAC tenant end-to-end. Useful for smoke tests and demos; not intended for production.

```bash
cd agent_client
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...    # or OPENAI_API_KEY
python agent.py
```

```
Connected! 50 tools available.

You: What models are available on this tenant?
Assistant: [Calling list_models] There are 3 models: ...

You: Show me EMEA revenue for Q1 where margin < 10%
Assistant: [Calling smart_query → read_fact_data] Here are the results (12 rows)...
```

---

## Development

Want to contribute? See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the full onboarding flow. The short version:

```bash
uv sync --extra dev                    # or: pip install -e ".[dev]"

uv run pytest tests/unit -q            # offline, all HTTP mocked with respx
uv run ruff check sac_mcp tests
uv run mypy sac_mcp
```

These three checks run in CI on Python 3.11 and 3.12 — green locally means green in CI.

Deeper references:

- [MAINTAINERS.md](MAINTAINERS.md) — internal conventions, recipes, security checklist, "definition of done"
- [docs/CONVENTIONS.md](docs/CONVENTIONS.md) — coding conventions with rationale
- [docs/SAC_API_NOTES.md](docs/SAC_API_NOTES.md) — SAC-specific API quirks
- [SECURITY.md](SECURITY.md) — vulnerability disclosure and operator best practices

---

## Project layout

```
sac_mcp/
├── server.py             # build_server(): registers all tools, resources, prompts
├── __main__.py           # entry point; reads MCP_TRANSPORT and dispatches
├── setup_cli.py          # interactive onboarding CLI
├── config.py             # Pydantic Settings; get_settings() is lru_cached
├── logging.py            # structlog + secret redaction
├── client/
│   ├── auth.py           # OAuthTokenProvider (2-legged, asyncio.Lock, 60 s leeway)
│   ├── csrf.py           # CsrfTokenCache; refresh on 403
│   ├── http.py           # SACClient: request, get_json, post_json, paginate
│   ├── odata.py          # ODataQuery builder (eq, contains, and_, or_, …)
│   ├── errors.py         # SACError + from_response() — normalises SAC error envelopes
│   ├── ratelimit.py      # async TokenBucket
│   └── models.py         # permissive Pydantic DTOs
├── tools/                # one file per SAC surface
│   ├── _common.py        # safe(), compact(), as_csv(), page_envelope()
│   ├── admin.py
│   ├── stories.py
│   ├── resources.py
│   ├── models.py
│   ├── dataexport.py
│   ├── aggregation.py    # server-side GROUP BY via OData $apply
│   ├── dataimport.py
│   ├── public_dimensions.py
│   ├── currency.py
│   ├── difference.py     # delta tracking
│   ├── widget_query.py
│   ├── sql_query.py      # SQL-like router (OData / Aggregation / Widget Query)
│   ├── smart_query.py    # plan-only NL→OData translator
│   ├── monitoring.py     # data freshness, row counts, job history
│   ├── users.py
│   ├── teams.py
│   ├── content_network.py
│   ├── calendar.py
│   ├── multiaction.py
│   └── audit.py
├── resources/            # MCP resources (read-only URIs)
│   ├── tenant.py         # sac://tenant/info
│   └── catalog.py        # sac://catalog/models (5-min cache)
├── prompts/              # MCP prompts
│   ├── explore_tenant.py
│   ├── plan_writeback.py
│   └── audit_drilldown.py
└── transports/
    ├── stdio.py
    └── http.py           # bearer-auth + optional CORS

tests/
├── conftest.py           # respx fixtures, auto-loaded env (SAC_MAX_RPS=0)
└── unit/                 # all tests use respx — no live network in CI
```

---

## Documentation

| File | What's in it |
|---|---|
| [README.md](README.md) | This page — overview, install, configure, run |
| [docs/tools.md](docs/tools.md) | Full per-tool reference (parameters, purpose, hints) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Detailed design rationale: auth flow, retry strategy, pagination model |
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | Coding conventions for contributors with reasoning |
| [docs/SAC_API_NOTES.md](docs/SAC_API_NOTES.md) | SAC-specific API quirks and known issues |
| [MAINTAINERS.md](MAINTAINERS.md) | Internal maintainer guide — recipes, security checklist, "definition of done" |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to set up, what to run before a PR, commit and PR conventions |
| [SECURITY.md](SECURITY.md) | Vulnerability disclosure channel and production hardening checklist |

---

## License

MIT — see [LICENSE](LICENSE) for details.
