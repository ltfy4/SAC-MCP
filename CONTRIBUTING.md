# Contributing to SAC-MCP

Thanks for considering a contribution. This project is small and opinionated — please read this page (and skim [MAINTAINERS.md](MAINTAINERS.md) once) before opening anything non-trivial.

## Ground rules

- **Open an issue first** for new features or behavior changes. Bug fixes, typo fixes, and docs improvements can go straight to a pull request.
- **One logical change per PR.** "Add feature X and refactor Y" should be two PRs.
- **No drive-by refactors.** If you touch a file for unrelated cleanup, mention it in the PR description so reviewers know what's intentional.
- **Don't push to `main`.** Use a `feat/<topic>` or `fix/<topic>` branch and open a PR.

## Development setup

```bash
# Clone and enter
git clone https://github.com/ltfy4/sac-mcp.git
cd sac-mcp

# Create a virtualenv (any standard tool works — venv / uv / pipenv)
python3.11 -m venv .venv
source .venv/bin/activate

# Install with dev extras
pip install -e ".[dev]"
```

You can run the server locally without a real SAC tenant — every unit test mocks HTTP via `respx`. A real tenant is only required for live integration tests (gated behind `SAC_LIVE_TEST=1`).

## What to run before opening a PR

The CI workflow runs these three checks on Python 3.11 and 3.12. Run them locally first:

```bash
ruff check sac_mcp tests
mypy sac_mcp
pytest tests/unit -q
```

All three must pass. If `mypy` complains about something genuinely intractable, add a narrow `# type: ignore[code]` with a one-line reason and move on — don't suppress whole files.

## Adding a new tool

The most common contribution. See the **"Recipe: Add a new tool to an existing surface"** section in [MAINTAINERS.md](MAINTAINERS.md) for the full pattern. Short version:

1. Find the right module in `sac_mcp/tools/<surface>.py` (or create one if the SAC surface is new).
2. Add an `async def` decorated with `@server.tool(annotations=ToolAnnotations(readOnlyHint=True))` (or `destructiveHint=True` for writes) and `@safe`.
3. Return a dict — collection results should go through `page_envelope(compact(rows))`.
4. Write a unit test in `tests/unit/test_<surface>.py` using `respx_mock`. Live tenant calls are not allowed in unit tests.
5. If the tool is user-facing, add it to the catalogue in `README.md` and `docs/tools.md`, and to the assertion set in `tests/unit/test_server_assembly.py`.

Deeper reasoning for *why* the conventions are what they are: [docs/CONVENTIONS.md](docs/CONVENTIONS.md). SAC-specific quirks: [docs/SAC_API_NOTES.md](docs/SAC_API_NOTES.md). High-level architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Commit messages

- Imperative mood: "Add foo", "Fix bar", "Document baz".
- Subject ≤ 70 characters.
- Body explains *why*, not *what* — the diff already shows the what.
- Use trailers (`Co-authored-by`, etc.) only when accurate.

## Pull requests

Include in the description:

- **What changed** (one paragraph, in plain English).
- **Why** (link the issue if one exists).
- **How you tested it** (the three CI checks at minimum; if it touches HTTP behavior, mention the respx scenarios you covered).

A reviewer will check that the PR matches the conventions above and that CI is green before merging.

## Security issues

Do **not** open a public issue for security problems. See [SECURITY.md](SECURITY.md) for the disclosure channel.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE) that covers the project.
