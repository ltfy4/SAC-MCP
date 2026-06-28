# Architecture

Deeper architectural notes for SAC-MCP. Shorter day-to-day rules live in `MAINTAINERS.md`; this file explains the **why**.

## High-level picture

```
┌──────────────────────────────────────────────────────────────┐
│                       MCP Client (LLM)                       │
│   Claude Desktop · MCP Inspector · custom client             │
└─────────────────────────┬────────────────────────────────────┘
                stdio  │  Streamable HTTP
                       │  (bearer-auth + optional CORS)
┌─────────────────────────▼────────────────────────────────────┐
│                       FastMCP server                         │
│  ─────────────────────────────────────────────────────────   │
│   Tools (50+)        Resources (sac://...)     Prompts       │
│  ─────────────────────────────────────────────────────────   │
│                       SACClient (single)                     │
│   OAuth (2-legged)  ·  CSRF cache  ·  retry/backoff          │
│   pagination        ·  token-bucket rate limit               │
│  ─────────────────────────────────────────────────────────   │
│                  Pydantic Settings (env-driven)              │
│                  structlog (JSON, redacted)                  │
└─────────────────────────┬────────────────────────────────────┘
                          │ HTTPS
                          ▼
                ┌─────────────────────┐
                │  SAP Analytics      │
                │  Cloud tenant       │
                │  (`*.cloud.sap`)    │
                └─────────────────────┘
```

## Why FastMCP and not the low-level MCP server?

FastMCP turns an annotated `async def` into an MCP tool with:
- A JSON Schema generated from Pydantic / type hints (no schema duplication)
- Title / description from the docstring
- `ToolAnnotations` (read-only / destructive hints) used by clients to gate confirmation prompts

For a server that wraps ~50 endpoints, the boilerplate savings are worth a small loss of flexibility.

## Why one `SACClient` instance

- A shared `httpx.AsyncClient` reuses connections (HTTP/2 multiplexing on a single TCP connection is a big win against a SAC tenant on the other side of an Atlantic link).
- One token cache, one CSRF cache, one rate-limit bucket. Two clients would mean two OAuth refreshes, double rate, race-y CSRF state.
- The client is created in `build_server(settings)` and closed when the server process exits.

## Auth flow (2-legged client_credentials)

```
   tool call
      │
      ▼
 SACClient.request()
      │
      ├── OAuthTokenProvider.get_token()
      │        │
      │        ├── cache hit? return
      │        └── cache miss / near expiry:
      │              acquire asyncio.Lock
      │              POST {AUTH}/oauth/token
      │              cache (access_token, expires_at)
      │
      ├── if non-GET: CsrfTokenCache.get()
      │        └── if empty: GET {TENANT}/api/v1/csrf
      │             with x-csrf-token: fetch
      │             read x-csrf-token response header
      │
      ├── send request with:
      │       Authorization: Bearer <token>
      │       x-sap-sac-custom-auth: true
      │       x-csrf-token: <token>   (writes only)
      │
      ├── 401 → invalidate token → retry once
      ├── 403 + csrf hint → invalidate CSRF → retry once
      ├── 429 / 5xx → tenacity retry (exponential backoff)
      └── ≥400 otherwise → raise SACError
```

### Why `x-sap-sac-custom-auth: true`

SAC normally negotiates a session cookie on first call. With our header, SAC treats every request as stateless — no `Set-Cookie`, so we never need a cookie jar. This dodges SAP KBA 3387282 (CSRF token issues when cookies aren't preserved) and 3566761 (Data Import 403 on third-party tools that drop cookies). Removing this header would re-introduce both bugs.

### Why a separate CSRF cache (not "fetch on every write")

`/api/v1/csrf` is cheap but synchronous. Caching it lets a write-heavy LLM session (e.g. a 10k-row import) avoid 10k extra round trips. Refresh-on-403 keeps us correct when SAC rotates the token.

## Pagination model

`SACClient.paginate(path, params, max_rows)`:

- Yields rows one at a time so callers can stop early.
- Looks for `@odata.nextLink` (OData) → `nextLink` → `next` (Public REST), in that order.
- Treats nextLink as the canonical follow-up URL — does not pass `params` again, since the link already encodes them.
- Caps with `max_rows` to keep the LLM context predictable.

## Error normalisation

SAC returns at least three error envelopes:

- OData v4 — `{"error": {"code": "...", "message": "..."}}`, sometimes `message` is `{"value": "..."}`
- SCIM — `{"detail": "...", "status": 4xx}`
- OAuth — `{"error": "...", "error_description": "..."}`

`from_response()` in `errors.py` handles all three, then attaches a one-line **hint** based on the status code (e.g. 401 → "OAuth token rejected — verify SAC_CLIENT_ID/SAC_CLIENT_SECRET and OAuth scope"). This is what the LLM ultimately sees, so it can react instead of getting stuck on opaque 4xx codes.

## Retry strategy

| Condition | Behaviour |
|---|---|
| Transport error (`httpx.TransportError`) | Retry with exponential backoff (`tenacity`) up to `SAC_MAX_RETRIES` |
| 429 / 502 / 503 / 504 | Retry with backoff (we honour `Retry-After` via tenacity's exponential wait) |
| 401 | Invalidate token, refresh, retry **once** in-line (not via tenacity) |
| 403 with CSRF hint on a write | Invalidate CSRF, refresh, retry **once** in-line |
| Other 4xx | Raise `SACError` immediately — no retry |
| 5xx other than the above | Raise `SACError` (tenacity does not retry these) |

## Rate limiting

A single `TokenBucket(rate=SAC_MAX_RPS)` gates every request. This is local-only — SAC's own quotas are tenant-wide, but local limiting prevents an LLM agent from hammering SAC during a buggy loop.

`SAC_MAX_RPS=0` in tests disables the bucket entirely.

## Transport: stdio vs Streamable HTTP

| | stdio | Streamable HTTP |
|---|---|---|
| Client | Claude Desktop and other local MCP clients | Anything that speaks Streamable HTTP |
| Auth (transport) | OS-level (whoever can run the binary) | Bearer (`MCP_HTTP_BEARER`) + optional CORS allowlist |
| State | Per-process | Per-process (server is multi-session-aware) |
| Logs | stderr (stdout is the protocol channel — never `print` there) | stderr |
| Use case | Single user, dev workstation | Hosted, team, behind a gateway |

Both transports consume the same `FastMCP` instance built by `build_server()`.

## Test architecture

- **Pure unit tests** for the OData builder, error parser, shaping helpers (no I/O).
- **`respx`-mocked tests** for the OAuth, CSRF, pagination and retry paths. The pattern: register an OAuth mock, register the SAC endpoint mocks, instantiate `SACClient` (no fakes — real client class, just mocked transport).
- **Server-assembly test** (`test_server_assembly.py`) builds the full FastMCP app and asserts: every expected tool name is present and has the right hint. This is the safety net for the "I forgot to register a module" failure.
- **No live tests in CI.** Live tests live in `tests/integration/` and run only when `SAC_LIVE_TEST=1`.

## Implemented features

- **Semantic NL→OData tool** — `smart_query(model_id, question)` reads the model's `$metadata`, extracts dimension/measure names, and returns a rule-based `read_fact_data` plan (filter, select, orderby, top) plus a rationale. The tool is **plan-only**: it never executes the query. The caller (or LLM) reviews the plan and explicitly invokes `read_fact_data` with the suggested arguments. That confirmation step is the safety boundary — the rule-based mapping can misinterpret a question, so we never let it touch tenant data on its own.

## Open extension points (none implemented yet)

These are deliberately **not** in the codebase — adding them is a future feature, not a bug fix:

- **3-legged OAuth** (`OAuthTokenProvider` would gain a redirect-URL flow)
- **Per-session SAC credentials** in HTTP transport (currently one tenant per server)
- **OpenTelemetry tracing & Prometheus metrics**
- **Caching layer with ETag** for `$metadata` and dimension lists
- **Story PNG/PDF export → MCP image resource**
- **Smart Predict integration**

When adding any of these, update this file and `MAINTAINERS.md` in the same change.
