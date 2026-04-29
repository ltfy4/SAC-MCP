"""Shared helpers for shaping SAC payloads into LLM-friendly results."""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable, Sequence

from sac_mcp.client.errors import SACError


# Row count above which we prefer CSV/markdown instead of a JSON list.
LARGE_ROW_THRESHOLD = 200


def safe(call):  # type: ignore[no-untyped-def]
    """Decorator that turns a :class:`SACError` into a tool-friendly dict.

    FastMCP serialises whatever the tool returns; we want errors to show up as a
    structured ``{"error": ...}`` rather than crashing the call.
    """

    async def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            return await call(*args, **kwargs)
        except SACError as exc:
            return {"error": exc.to_tool_message(), "code": exc.code, "status": exc.status_code}

    wrapper.__name__ = call.__name__
    wrapper.__doc__ = call.__doc__
    wrapper.__wrapped__ = call  # type: ignore[attr-defined]
    return wrapper


def compact(rows: Iterable[dict[str, Any]], keys: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Drop ``None`` and (optionally) project to a subset of keys."""

    out: list[dict[str, Any]] = []
    for r in rows:
        if keys is not None:
            row = {k: r.get(k) for k in keys}
        else:
            row = {k: v for k, v in r.items() if v is not None}
        out.append(row)
    return out


def as_csv(rows: Sequence[dict[str, Any]]) -> str:
    """Serialise rows as CSV. Unions the columns of every row."""

    if not rows:
        return ""
    columns: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                columns.append(k)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: _scalar(r.get(k)) for k in columns})
    return buf.getvalue()


def as_markdown_table(rows: Sequence[dict[str, Any]], max_rows: int = 50) -> str:
    """Render the first ``max_rows`` rows as a Markdown table."""

    if not rows:
        return "_(empty result)_"
    cols: list[str] = []
    seen: set[str] = set()
    for r in rows[:max_rows]:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                cols.append(k)
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = "\n".join(
        "| " + " | ".join(_md_cell(r.get(c)) for c in cols) + " |" for r in rows[:max_rows]
    )
    suffix = ""
    if len(rows) > max_rows:
        suffix = f"\n\n_(+{len(rows) - max_rows} more rows truncated)_"
    return f"{head}\n{sep}\n{body}{suffix}"


def _scalar(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return str(value)
    return value


def _md_cell(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).replace("|", "\\|").replace("\n", " ")
    return s


def page_envelope(
    rows: list[dict[str, Any]],
    *,
    next_cursor: str | None = None,
    total: int | None = None,
) -> dict[str, Any]:
    env: dict[str, Any] = {"rows": rows, "row_count": len(rows)}
    if next_cursor:
        env["next_cursor"] = next_cursor
    if total is not None:
        env["total"] = total
    return env
