# MAINTAINERS.md

Internal notes for maintainers and contributors working on **SAC-MCP** — the SAP Analytics Cloud Model Context Protocol server. Read this before opening a non-trivial pull request.

## What this project is

A Python MCP server that exposes the full SAP Analytics Cloud (SAC) public API surface (Public REST, Data Export OData v4, Data Import jobs, SCIM users/teams, Content Network, Calendar Tasks, Data Actions, Multi-Action, Audit, Monitoring) as MCP tools, resources and prompts.

It is consumed by any MCP-compatible client. Two transports are supported: `stdio` (local) and Streamable HTTP (remote / hosted).

## Tech stack

- **Python 3.11+** (no dependency on 3.12-only features)
- **`mcp[cli]`** (FastMCP interface) — tool/resource/prompt registration
- **`httpx[http2]`** — single async client for all SAC HTTP traffic
- **`pydantic` v2 + `pydantic-settings`** — typed tool params, env-driven config
- **`tenacity`** — retry with exponential backoff
- **`structlog`** — JSON logging with secret redaction
- **`uvicorn` + `starlette`** — Streamable HTTP transport host
- **`pytest` + `pytest-asyncio` + `respx`** — async HTTP mocking for tests

## Repo layout (must know)

```
sac_mcp/
├── server.py              # build_server(): single FastMCP app, registers everything
├── __main__.py            # entry point; reads MCP_TRANSPORT and dispatches
├── setup_cli.py           # interactive onboarding CLI (writes .env, prints client config)
├── config.py              # Pydantic settings, env vars, get_settings() (lru_cache)
├── logging.py             # structlog setup + redaction list
├── client/                # SAC HTTP layer — reused by every tool
│   ├── auth.py            # OAuthTokenProvider (2-legged, asyncio.Lock, 60s leeway)
│   ├── csrf.py            # CsrfTokenCache; refreshed on 403
│   ├── http.py            # SACClient: request, get_json, post_json, paginate
│   ├── odata.py           # ODataQuery + and_/or_/eq/contains/... builders
│   ├── errors.py          # SACError + from_response() (normalises envelopes)
│   ├── ratelimit.py       # async TokenBucket
│   └── models.py          # permissive Pydantic DTOs (SACEntity etc.)
├── tools/                 # MCP tools, ONE MODULE PER SAC SURFACE
│   ├── _common.py         # safe() decorator, compact(), as_csv(), as_markdown_table(), page_envelope()
│   ├── admin.py           # whoami, tenant_info, health_check
│   ├── stories.py
│   ├── resources.py       # /filerepository/Resources
│   ├── models.py          # data-export Administration namespace
│   ├── dataexport.py      # fact / master / audit OData reads (+ delta + CSV)
│   ├── aggregation.py     # server-side GROUP BY via OData $apply
│   ├── dataimport.py      # job lifecycle (create / upload / validate / run / status / cancel) + one-shot write_fact_data
│   ├── dataactions.py     # planning data actions (list / inspect / trigger / poll)
│   ├── difference.py      # snapshot delta between two date ranges
│   ├── currency.py        # tenant currency conversion + exchange-rate reads
│   ├── public_dimensions.py # public dimension members
│   ├── widget_query.py    # story widget data reads
│   ├── sql_query.py       # SQL-like router (OData / Aggregation / Widget Query)
│   ├── smart_query.py     # plan-only natural-language query translator
│   ├── monitoring.py      # data-freshness, row counts, job history
│   ├── users.py           # SCIM Users
│   ├── teams.py           # SCIM Groups
│   ├── content_network.py
│   ├── calendar.py
│   ├── multiaction.py
│   └── audit.py
├── resources/             # MCP resources (read-only URIs)
│   ├── tenant.py          # sac://tenant/info
│   └── catalog.py         # sac://catalog/models (5-min cache)
├── prompts/               # MCP prompts
│   ├── explore_tenant.py
│   ├── plan_writeback.py
│   └── audit_drilldown.py
└── transports/
    ├── stdio.py
    └── http.py            # bearer-auth + optional CORS

tests/
├── conftest.py            # respx-based fixtures, auto-loaded env
└── unit/                  # all tests use respx, no live network
```

## Conventions (follow these — they're already established)

### Tool modules
- **One file per SAC surface.** Don't merge unrelated tools.
- Each module exposes `def register(server: FastMCP, client: SACClient) -> None`.
- All tools are **`async def`**, return a `dict[str, Any]`.
- Decorate every tool with **`@safe`** (from `tools/_common.py`) — converts `SACError` into a structured `{"error": ...}` dict so the caller can react.
- Decorate with **`@server.tool(annotations=ToolAnnotations(...))`** — apply `readOnlyHint=True` to every read tool, `destructiveHint=True` to every write/mutate tool. This is how MCP clients decide whether to confirm.
- Tool **docstrings** become the caller-facing description — write them in plain English, with Args sections when parameters need clarification.
- Tool **parameter types** drive the JSON schema; prefer `Literal[...]` for enums, `int | None = None` for optionals.

### Pagination & shaping
- Always use `client.paginate(...)` for list endpoints — it follows OData `@odata.nextLink` and Public-REST cursors automatically.
- Cap responses with `max_rows`/`top`. **Default to ≤ 200 rows** so the calling context stays small.
- Use `compact(rows)` to drop `None` keys; `as_csv` / `as_markdown_table` for big tables; `page_envelope(rows, next_cursor=...)` for the canonical return shape `{"rows": [...], "row_count": N, "next_cursor": ...}`.

### HTTP client
- **Never** instantiate your own `httpx.AsyncClient` inside a tool — always go through the shared `SACClient` passed into `register()`.
- For raw GETs use `client.get_json(path, params=...)`.
- For writes use `client.post_json` / `patch_json` / `delete` — these handle CSRF transparently.
- For list endpoints use `client.paginate(path, params=..., max_rows=N)`.

### OData filters
- Build with `from sac_mcp.client.odata import ODataQuery, eq, contains, and_, or_`.
- Don't string-concatenate filters by hand — use the helpers; they escape quotes correctly (see `quote_odata_string`).

### SAC-specific gotchas (LEARN THESE)
- **`x-sap-sac-custom-auth: true`** is set automatically on every request. Do **not** remove it — it tells SAC to skip session-cookie negotiation, which avoids the well-known KBA 3387282 / 3566761 "missing set-cookie" failure mode.
- **CSRF tokens** are required for every non-GET. `SACClient` fetches them lazily and refreshes on 403 with `x-csrf-token: required`. New write tools get this for free.
- **OAuth 401 handling**: `SACClient` invalidates and re-fetches the token once on 401, then retries. Don't add another retry layer.
- The `/api/v1/csrf` GET path is the canonical "any cheap GET" — used both for CSRF acquisition and `health_check`.
- Model IDs in the Data Export API show up under namespace `sac`: full path is `/api/v1/dataexport/providers/sac/{model_id}/...`.

### Errors
- Tools should NOT swallow exceptions silently. Let `SACError` propagate — `@safe` will convert it.
- For non-SAC errors (programmer mistakes, bad inputs), let them raise; pytest will catch them and they'll show as a 500 on the MCP transport.

### Logging
- Use `from sac_mcp.logging import get_logger` — never use the stdlib `logging` directly. (Would bypass redaction.)
- The redactor in `logging.py` strips `authorization`, `x-csrf-token`, `set-cookie`, `client_secret`, `access_token`, `refresh_token`. If you log a new sensitive key, **add it to `_REDACT_KEYS`**.

### Config
- All runtime knobs go through `Settings` (Pydantic). New env vars must be declared there with a sensible default.
- `get_settings()` is `lru_cache`d — tests call `get_settings.cache_clear()` in the autouse `_env` fixture.
- Stay env-only — don't read JSON config files at runtime.

## Common commands

```bash
# Install
pip install -e ".[dev]"

# Run (stdio, default)
sac-mcp

# Run (Streamable HTTP)
MCP_TRANSPORT=http MCP_HTTP_BEARER=$(openssl rand -hex 16) sac-mcp

# Unit tests (offline, mocked HTTP)
pytest tests/unit -q

# One test
pytest tests/unit/test_http_client.py::test_csrf_refresh_on_403 -v

# Lint & type check
ruff check sac_mcp tests
mypy sac_mcp

# MCP Inspector (interactive)
npx @modelcontextprotocol/inspector sac-mcp

# Live integration (requires real tenant creds in .env)
SAC_LIVE_TEST=1 pytest tests/integration -q -m live
```

## Recipe: "Add a new tool to an existing surface"

1. Open the right `tools/<surface>.py` (e.g. `dataexport.py` for Data Export).
2. Inside the existing `register(server, client)` function, add:
   ```python
   @server.tool(annotations=ToolAnnotations(readOnlyHint=True))  # or destructiveHint=True
   @safe
   async def my_new_tool(model_id: str, top: int = 100) -> dict[str, Any]:
       """One-line summary. Optional Args section if non-obvious."""
       rows: list[dict[str, Any]] = []
       async for r in client.paginate(
           f"/api/v1/.../{model_id}/Whatever",
           params=ODataQuery(top=top).to_params(),
           max_rows=top,
       ):
           rows.append(r)
       return page_envelope(compact(rows))
   ```
3. Add a unit test in `tests/unit/test_<surface>.py` (create if needed). Use `respx_mock` for mocking. Do **not** rely on a live tenant in unit tests.
4. Add the new tool to the assertion set in `tests/unit/test_server_assembly.py` if it's a major addition.
5. Run `pytest tests/unit -q` — must pass before commit.

## Recipe: "Add a whole new SAC surface"

1. Create `sac_mcp/tools/<surface>.py` with the `register(server, client)` skeleton (copy any existing module's structure — `audit.py` is a small, clean reference).
2. Import & call `<surface>.register(server, client)` from `sac_mcp/server.py`'s registration loop.
3. Add tools per the recipe above.
4. If the surface needs a brand-new client method (e.g. multipart upload), add it to `client/http.py` — keep tools thin.
5. Document the new endpoint family in the README under the tool catalogue.

## Things to avoid

- **Don't** add new top-level dependencies without a clear reason — every dep is a supply-chain risk for an enterprise tool.
- **Don't** widen permission scopes silently. If a new tool needs a SAC role beyond what existing tools require, document it.
- **Don't** `print(...)` for stdio transport — stdout is the protocol channel. Logs go to stderr (handled by `logging.py`).
- **Don't** create files outside `sac_mcp/` and `tests/` without a reason. README, pyproject, Dockerfile, `.github/` are the only top-level files.
- **Don't** instantiate `SACClient` in tests — use the `client` fixture from `conftest.py`.
- **Don't** call live SAC from unit tests. Live tests live under `tests/integration/` and are gated by the `live` pytest marker + `SAC_LIVE_TEST=1`.
- **Don't** hardcode tenant URLs. Always read from `Settings`.
- **Don't** add 3-legged OAuth or refresh-token logic to `auth.py` without first opening an issue — the project commits to 2-legged client_credentials only for v1.
- **Don't** push to `main`/`master` directly. Feature work goes on `feat/...` branches with a pull request.
- **Don't** commit `.env` (already in `.gitignore`), credentials, real tenant URLs, or recorded HTTP fixtures with PII.
- **Don't** use emojis in code, comments, commits, or docs unless explicitly requested.

## Testing rules

- Every new client capability needs a unit test using `respx`.
- When mocking pagination with respx, **register the most-specific route first** (e.g. with `params={"page": "2"}` before the bare route). respx matches in registration order; bare routes match anything and create infinite loops.
- The `_env` fixture in `conftest.py` is `autouse=True` — it sets fake creds and `SAC_MAX_RPS=0` (rate limiting off in tests). Don't fight it.
- Async tests need `@pytest.mark.asyncio` (or rely on `asyncio_mode = "auto"` already set in `pyproject.toml`).

## Security checklist for any change

- [ ] No new env var exposes a secret without `SecretStr`.
- [ ] No new logged value contains tokens, passwords, cookies, or raw request bodies with PII.
- [ ] If a new tool can mutate the tenant, it has `destructiveHint=True`.
- [ ] If a new tool reads PII (users, audit log), it caps row counts and supports paging.
- [ ] No raw `eval`, `exec`, `subprocess` with user-controlled input. We don't run shell commands; this should never come up.

## What "done" looks like for a typical change

1. Code change is self-contained (no drive-by refactors).
2. `pytest tests/unit -q` is green.
3. `ruff check sac_mcp tests` is clean.
4. `mypy sac_mcp` is clean (or annotated with a `# type: ignore[code]` and a one-line reason).
5. Tool count and hint assertions in `test_server_assembly.py` still pass.
6. README's tool catalogue mentions any newly added user-facing tools.
7. Commit message explains *why*, not *what*.
8. Pushed to the feature branch only — never to `main` without an approved PR.

## Roadmap

Future enhancements (3-legged OAuth, semantic NL→OData, OpenTelemetry, story rendering, Datasphere, Helm chart, etc.) belong in a separate `ROADMAP.md` if/when added — don't sneak roadmap items into feature branches.
