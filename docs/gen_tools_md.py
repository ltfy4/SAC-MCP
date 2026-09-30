"""Regenerate docs/tools.md from the tools the server actually registers.

Run from the repo root:  python docs/gen_tools_md.py
"""

from __future__ import annotations

import importlib
import inspect
import pathlib
from typing import Any

SECTIONS = [
    ("admin", "Admin"),
    ("stories", "Stories"),
    ("resources", "Resources (file repository)"),
    ("models", "Models"),
    ("dataexport", "Data Export"),
    ("difference", "Delta tracking"),
    ("aggregation", "Aggregation"),
    ("fpa", "FP&A analysis"),
    ("sql_query", "Query routing: sql_query"),
    ("smart_query", "Query routing: smart_query"),
    ("dataimport", "Data Import"),
    ("multiaction", "Multi-Actions"),
    ("dataactions", "Data Actions"),
    ("currency", "Currency & unit tables"),
    ("public_dimensions", "Public dimensions"),
    ("users", "Users (SCIM)"),
    ("teams", "Teams (SCIM)"),
    ("calendar", "Calendar"),
    ("content_network", "Content transport"),
    ("audit", "Audit log"),
    ("monitoring", "Monitoring"),
    ("widget_query", "Widget query"),
]


def _collect(module_name: str) -> list[tuple[Any, Any]]:
    found: list[tuple[Any, Any]] = []

    class _Stub:
        def tool(self, *args: Any, annotations: Any = None, **kwargs: Any) -> Any:
            def deco(fn: Any) -> Any:
                found.append((fn, annotations))
                return fn

            return deco

    module = importlib.import_module(f"sac_mcp.tools.{module_name}")
    module.register(_Stub(), None)
    return found


def _params(fn: Any) -> str:
    parts = []
    for name, param in inspect.signature(fn).parameters.items():
        parts.append(f"`{name}`" if param.default is inspect.Parameter.empty else f"`{name}?`")
    return ", ".join(parts) or "-"


def _summary(fn: Any) -> str:
    doc = inspect.getdoc(fn) or ""
    first = doc.split("\n\n", 1)[0]
    return " ".join(first.split()).replace("|", "\\|")


def main() -> None:
    blocks: list[str] = []
    total = 0
    for module_name, title in SECTIONS:
        tools = _collect(module_name)
        total += len(tools)
        blocks.append(f"## {title}\n\n| Tool | Kind | Parameters (`?` = optional) | Description |\n|---|---|---|---|")
        for fn, ann in tools:
            kind = "write" if getattr(ann, "destructiveHint", False) else "read"
            blocks.append(f"| `{fn.__name__}` | {kind} | {_params(fn)} | {_summary(fn)} |")
        blocks.append("")
    header = (
        "# Tool reference\n\n"
        "Generated from the code by `python docs/gen_tools_md.py` -- do not edit by hand.\n\n"
        f"{total} tools. **read** tools carry `readOnlyHint`; **write** tools carry "
        "`destructiveHint`, so MCP clients ask before running them.\n"
    )
    out = pathlib.Path(__file__).with_name("tools.md")
    out.write_text(header + "\n" + "\n".join(blocks), encoding="utf-8")
    print(f"wrote {out} ({total} tools)")


if __name__ == "__main__":
    main()
