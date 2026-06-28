# Coding conventions

This is the long-form companion to the "Conventions" section in `MAINTAINERS.md`. Skim `MAINTAINERS.md` for the rules; come here when you want the reasoning.

## File & module layout

- **One SAC surface = one module under `sac_mcp/tools/`.** Don't merge "calendar" into "admin" because they're both small. Surfaces are the unit of evolution; SAC adds endpoints to one without changing others.
- **Cross-cutting helpers** live in `tools/_common.py`. If you find yourself copying a 5-line helper across two tool modules, promote it.
- **HTTP capabilities** live in `client/http.py`. Tools should never instantiate `httpx` directly.

## Tool design

### Naming
- Verb-first, snake_case: `list_models`, `read_fact_data`, `create_import_job`, `cancel_job`.
- Read tools: `list_…`, `get_…`, `read_…`, `search_…`, `find_…`.
- Write tools: `create_…`, `update_…`, `delete_…`, `add_…`, `remove_…`, `run_…`, `cancel_…`, `deactivate_…`.
- Don't prefix with the surface name — the LLM already sees them grouped via descriptions.

### Parameters
- Required positional first, optional kwargs after.
- Prefer `Literal[...]` over free-form strings for enums (SAC has many).
- Default `top` / `max_rows` to ≤ 200; let users widen.
- Never accept a raw URL; accept IDs and build the URL inside the tool.

### Return shape
- For collection-like results: `page_envelope(rows, next_cursor=...)` → `{"rows": [...], "row_count": N, "next_cursor": ...}`.
- For singletons: return the SAC payload as-is (or normalised through `compact()`).
- For very large tables: return CSV via `as_csv(rows)` and put the size in `row_count`.

### Errors
- Don't `try/except SACError` — `@safe` already does this and it produces a uniform error shape.
- `try/except Exception` only when you *know* you have a sensible fallback (see `whoami` falling back to a model-list call when `/scim/Me` is unavailable).

### Annotations
- `readOnlyHint=True` for any tool that doesn't mutate the tenant.
- `destructiveHint=True` for any tool that mutates state, even if the mutation is reversible (e.g. `add_member`).
- `idempotentHint` and `openWorldHint` are available but unused so far — add them if you have a clear use case.

## Type hints

- Project-wide: `from __future__ import annotations` at the top of every Python file.
- Use `dict[str, Any]`, `list[...]`, `str | None` (PEP 604) — we're 3.11+.
- Don't over-type. SAC payloads are open dicts; modelling them with strict Pydantic schemas burns time and breaks on minor SAC releases.

## Async

- Everything I/O is async. There is no sync HTTP path.
- Don't sprinkle `asyncio.sleep(...)` to "wait for" SAC — use `httpx`'s built-in retry hooks via tenacity instead.
- Locks: `OAuthTokenProvider` and `CsrfTokenCache` use `asyncio.Lock`. Don't add a second lock around them.

## Logging

- Levels: `info` for one-shot lifecycle events (server start, transport mode); `debug` for per-request detail; `warning` for recoverable degradation; `error` for raised exceptions you can't normalise.
- Structured fields are encouraged: `_log.info("oauth.fetch", url=url, scope=scope)`. The JSON renderer makes them queryable.
- If you log a new key whose value is sensitive, **add it to `_REDACT_KEYS` in `logging.py`** before merging.

## Tests

### Layout
- One test file per source module is the ideal: `test_<topic>.py`. Don't write 800-line "test_everything.py" files.
- Fixtures shared across files go in `conftest.py`.

### Mocking
- Use `respx_mock` (the pytest fixture) for HTTP. Don't monkey-patch httpx.
- For pagination tests: register the **most-specific** route first. respx matches in registration order; a bare route swallows everything.
- For OAuth: pre-register the token endpoint in your test (or use the `mock_oauth` fixture).

### Assertions
- Prefer asserting tool **outputs** over asserting URLs/headers — exception: when the test's purpose is to verify the headers (`test_get_attaches_bearer_and_custom_auth_header`).
- For server-assembly tests, assert **tool names + hints** rather than full schemas — schemas are derived from type hints and shouldn't be redundantly tested.

## Commits

- Imperative mood: "Add foo", "Fix bar", "Document baz".
- Subject line ≤ 70 chars.
- Body explains *why*, not *what* (the diff shows the what).
- One logical change per commit. If you're tempted to write "and also", split it.
- Trailers (`Co-authored-by`, etc.) only when accurate.

## Branches

- `main` — releasable.
- `feat/<topic>` or `fix/<topic>` — short-lived feature branches.
- Don't push directly to `main`; use a PR.
- Force-push only on your own feature branch, only with `--force-with-lease`.

## Dependencies

- Every new dep is a supply-chain risk. Justify it.
- Pin **major** versions in `pyproject.toml` (`>=X.Y`), let minor float.
- Dev-only deps go under `[project.optional-dependencies].dev`.

## Public API stability

The MCP tool catalogue is the public API. Don't:
- Rename a tool without a deprecation period.
- Remove a parameter that was previously required.
- Change a return shape from a list to a dict (or vice versa) in a non-major release.

Adding new tools, new optional parameters, and new fields to a return dict are all safe.
