"""Interactive setup CLI for SAC-MCP configuration.

Prompts the user for SAC credentials and transport options, writes a .env file,
and prints a Claude Desktop config snippet ready to paste.
"""

from __future__ import annotations

import getpass
import json
import re
import secrets
import shutil
import sys
from pathlib import Path
from typing import TextIO

_REGION_RE = re.compile(r"\.(eu10|us10|ap10|ap11|jp10|br10|ca10|eu11|us20|us21)\.")


def _extract_region(url: str) -> str | None:
    m = _REGION_RE.search(url)
    return m.group(1) if m else None


def _prompt(label: str, *, default: str = "", stream: TextIO = sys.stdin) -> str:
    suffix = f" [{default}]" if default else ""
    sys.stderr.write(f"{label}{suffix}: ")
    sys.stderr.flush()
    value = stream.readline().strip()
    return value or default


def _validate_https(url: str, name: str) -> bool:
    if not url.startswith("https://"):
        sys.stderr.write(f"WARNING: {name} should use https (got {url!r})\n")
        return False
    return True


def _check_region_match(tenant_url: str, auth_url: str) -> None:
    t_region = _extract_region(tenant_url)
    a_region = _extract_region(auth_url)
    if t_region and a_region and t_region != a_region:
        sys.stderr.write(
            f"WARNING: Region mismatch — tenant uses {t_region} but auth uses {a_region}. "
            f"This is a common cause of 401 errors.\n"
        )


def _resolve_sac_mcp_command() -> tuple[list[str], str | None]:
    path = shutil.which("sac-mcp")
    if path:
        return [path], None
    return [sys.executable, "-m", "sac_mcp"], (
        "NOTE: sac-mcp not found on PATH; using python -m sac_mcp instead. "
        "Install with 'pip install -e .' to get the console script."
    )


def _build_env_content(values: dict[str, str]) -> str:
    lines: list[str] = []
    for key, val in values.items():
        lines.append(f"{key}={val}")
    return "\n".join(lines) + "\n"


def _build_claude_desktop_snippet(
    command: list[str], env_vars: dict[str, str]
) -> str:
    snippet = {
        "mcpServers": {
            "sac": {
                "command": command[0],
                "args": command[1:] if len(command) > 1 else [],
                "env": env_vars,
            }
        }
    }
    return json.dumps(snippet, indent=2)


def main(*, _input: TextIO | None = None) -> None:
    """Entry point for sac-mcp-setup console script."""
    stream = _input or sys.stdin

    sys.stderr.write("SAC-MCP Setup\n")
    sys.stderr.write("=" * 40 + "\n\n")

    tenant_url = _prompt("SAC tenant URL (e.g. https://company.eu10.hcs.cloud.sap)", stream=stream)
    _validate_https(tenant_url, "SAC_TENANT_URL")

    auth_url = _prompt(
        "OAuth auth URL (e.g. https://company.authentication.eu10.hana.ondemand.com)",
        stream=stream,
    )
    _validate_https(auth_url, "SAC_AUTH_URL")
    _check_region_match(tenant_url, auth_url)

    client_id = _prompt("OAuth client ID", stream=stream)

    if _input is not None:
        client_secret = stream.readline().strip()
    else:
        client_secret = getpass.getpass("OAuth client secret: ")

    oauth_scope = _prompt("OAuth scope (optional, press Enter to skip)", stream=stream)

    sys.stderr.write("\nTransport: stdio (default) or http?\n")
    transport = _prompt("Transport [stdio/http]", default="stdio", stream=stream).lower()

    env_values: dict[str, str] = {
        "SAC_TENANT_URL": tenant_url,
        "SAC_AUTH_URL": auth_url,
        "SAC_CLIENT_ID": client_id,
        "SAC_CLIENT_SECRET": client_secret,
    }

    if oauth_scope:
        env_values["SAC_OAUTH_SCOPE"] = oauth_scope

    if transport == "http":
        http_host = _prompt("HTTP host", default="127.0.0.1", stream=stream)
        http_port = _prompt("HTTP port", default="8080", stream=stream)
        bearer = secrets.token_hex(32)
        env_values["MCP_TRANSPORT"] = "http"
        env_values["MCP_HTTP_HOST"] = http_host
        env_values["MCP_HTTP_PORT"] = http_port
        env_values["MCP_HTTP_BEARER"] = bearer

    cwd = Path.cwd()
    env_path = cwd / ".env"
    if env_path.exists():
        env_path = cwd / ".env.generated"
        sys.stderr.write(
            f"\n.env already exists — writing to {env_path.name} instead.\n"
        )

    env_path.write_text(_build_env_content(env_values))
    sys.stderr.write(f"Configuration written to {env_path}\n\n")

    command, note = _resolve_sac_mcp_command()
    claude_env = {
        "SAC_TENANT_URL": tenant_url,
        "SAC_AUTH_URL": auth_url,
        "SAC_CLIENT_ID": client_id,
        "SAC_CLIENT_SECRET": client_secret,
    }

    snippet = _build_claude_desktop_snippet(command, claude_env)
    sys.stdout.write("Claude Desktop config snippet (paste into claude_desktop_config.json):\n\n")
    sys.stdout.write(snippet + "\n")

    if note:
        sys.stdout.write(f"\n{note}\n")

    sys.stdout.write("\nNext steps: see README.md for transport options and the full tool catalogue.\n")


if __name__ == "__main__":
    main()
