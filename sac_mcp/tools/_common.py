"""Shared helpers for shaping SAC payloads into LLM-friendly results."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from sac_mcp.client.errors import SACError
from sac_mcp.config import get_settings

if TYPE_CHECKING:
    from sac_mcp.client.http import SACClient

# Row count above which we prefer CSV/markdown instead of a JSON list.
LARGE_ROW_THRESHOLD = 200


def safe(call):  # type: ignore[no-untyped-def]
    """Decorator that turns a :class:`SACError` into a tool-friendly dict.

    FastMCP serialises whatever the tool returns; we want errors to show up as a
    structured ``{"error": ...}`` rather than crashing the call.
    """

    async def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            return fit_response(await call(*args, **kwargs))
        except SACError as exc:
            return {"error": exc.to_tool_message(), "code": exc.code, "status": exc.status_code}
        except ValueError as exc:
            # Bad tool input (e.g. an unsupported aggregation operator) — hand
            # the LLM a structured error it can correct, not a traceback.
            return {"error": f"Invalid input: {exc}", "code": "invalid_input"}

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
        for k in r:
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
        for k in r:
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
    has_more: bool | None = None,
) -> dict[str, Any]:
    env: dict[str, Any] = {"rows": rows, "row_count": len(rows)}
    if next_cursor:
        env["next_cursor"] = next_cursor
    if total is not None:
        env["total"] = total
    if has_more is not None:
        env["has_more"] = has_more
        if has_more:
            env["hint"] = "More rows exist — narrow the filter or raise top/max_rows."
    return env


async def collect(
    client: SACClient,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    max_rows: int,
    set_top: bool = True,
) -> tuple[list[dict[str, Any]], bool]:
    """Read up to ``max_rows`` rows and report whether more exist.

    Asks the server for one extra row (``$top=max_rows+1``) so ``has_more`` is
    exact without an extra round trip.
    """

    max_rows = max(1, max_rows)
    query = dict(params or {})
    if set_top:
        query["$top"] = str(max_rows + 1)
    rows: list[dict[str, Any]] = []
    async for row in client.paginate(path, params=query, max_rows=max_rows + 1):
        rows.append(row)
    return rows[:max_rows], len(rows) > max_rows


async def read_rows_any(
    client: SACClient,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    max_rows: int = 200,
) -> dict[str, Any]:
    """Read an endpoint that may answer JSON, CSV or plain text.

    SAC's audit export and monitoring endpoints reject ``Accept:
    application/json`` with 406, so ask for anything and parse by content type.
    """

    ctype, body = await client.get_text(
        path, params=params, accept="application/json, text/csv;q=0.9, */*;q=0.8"
    )
    rows: list[dict[str, Any]] | None = None
    if "json" in ctype or body.lstrip()[:1] in ("{", "["):
        payload = json.loads(body) if body.strip() else {}
        if isinstance(payload, list):
            rows = [r for r in payload if isinstance(r, dict)]
        elif isinstance(payload, dict) and isinstance(payload.get("value"), list):
            rows = [r for r in payload["value"] if isinstance(r, dict)]
        else:
            return {"content_type": ctype, "data": payload}
    elif "csv" in ctype:
        rows = list(csv.DictReader(io.StringIO(body)))
    if rows is None:
        return {"content_type": ctype, "text": body}
    return {"content_type": ctype, **page_envelope(rows[:max_rows], has_more=len(rows) > max_rows)}


def fit_response(result: Any) -> Any:
    """Keep a tool result under ``SAC_RESPONSE_CHAR_LIMIT`` characters.

    Drops trailing rows (or CSV lines) rather than letting a single call blow
    the client's context window — a delta read once returned over 1 MB.
    """

    limit = get_settings().sac_response_char_limit
    if limit <= 0 or not isinstance(result, dict):
        return result
    size = len(json.dumps(result, default=str))
    if size <= limit:
        return result
    budget = limit - 400  # room for the note fields below

    rows = result.get("rows")
    if isinstance(rows, list) and rows:
        lo, hi = 0, len(rows)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(json.dumps({**result, "rows": rows[:mid]}, default=str)) <= budget:
                lo = mid
            else:
                hi = mid - 1
        return {
            **result,
            "rows": rows[:lo],
            "row_count": lo,
            "has_more": True,
            "truncated": True,
            "note": (
                f"Truncated to {lo} of {len(rows)} rows to stay under {limit} characters; "
                "narrow the query (filter, select, top)."
            ),
        }

    csv_text = result.get("csv")
    if isinstance(csv_text, str):
        cut = csv_text[:budget]
        cut = cut[: cut.rfind("\n") + 1] if "\n" in cut else cut
        return {
            **result,
            "csv": cut,
            "truncated": True,
            "note": f"CSV truncated to stay under {limit} characters; narrow the query.",
        }

    return {
        "truncated": True,
        "note": f"Result exceeded {limit} characters and was cut; narrow the query.",
        "preview": json.dumps(result, default=str)[:budget],
    }
