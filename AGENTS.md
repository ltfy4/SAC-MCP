# AGENTS.md

This file mirrors `CLAUDE.md` for tools that follow the generic AGENTS.md spec (e.g. Cursor, Aider, Cline, OpenAI Codex). Treat it as a pointer.

> **The single source of truth for project conventions is [`CLAUDE.md`](./CLAUDE.md). Read that first.**

## Quick reference

- **Language / runtime**: Python 3.11+
- **Package manager**: `pip` / `uv` (either works); deps in `pyproject.toml`
- **Install**: `pip install -e ".[dev]"`
- **Run**: `sac-mcp` (stdio) or `MCP_TRANSPORT=http MCP_HTTP_BEARER=… sac-mcp`
- **Tests**: `pytest tests/unit -q`
- **Lint**: `ruff check sac_mcp tests`
- **Types**: `mypy sac_mcp`
- **MCP inspector**: `npx @modelcontextprotocol/inspector sac-mcp`

## Where to put things

- New SAC tool on an existing surface → add to `sac_mcp/tools/<surface>.py`'s `register()`.
- Brand-new SAC surface → new module under `sac_mcp/tools/`, registered from `sac_mcp/server.py`.
- New shared HTTP capability → `sac_mcp/client/http.py`.
- New env var → declare on `Settings` in `sac_mcp/config.py`.
- New unit test → `tests/unit/test_<topic>.py`, mocked with `respx`.

## Non-negotiables

- Every tool has a clear docstring (LLM-facing description).
- Every tool is decorated with `@safe` and `@server.tool(annotations=ToolAnnotations(...))`.
- Read tools → `readOnlyHint=True`. Write/mutate tools → `destructiveHint=True`.
- Never bypass `SACClient` — it owns auth, CSRF, retry, rate-limit and pagination.
- Never log secrets. Add new sensitive header names to `_REDACT_KEYS` in `sac_mcp/logging.py`.
- Never use emojis unless explicitly requested.

For the full list of conventions, gotchas, recipes and security checklist, see [`CLAUDE.md`](./CLAUDE.md).
