"""Tests for the row-shaping helpers in :mod:`sac_mcp.tools._common`."""

from __future__ import annotations

from sac_mcp.tools._common import as_csv, as_markdown_table, compact, page_envelope


def test_compact_drops_none_keys() -> None:
    out = compact([{"a": 1, "b": None}, {"a": 2, "c": "x"}])
    assert out == [{"a": 1}, {"a": 2, "c": "x"}]


def test_compact_projects_to_keys() -> None:
    out = compact([{"a": 1, "b": 2}], keys=["a"])
    assert out == [{"a": 1}]


def test_csv_unions_columns() -> None:
    out = as_csv([{"a": 1, "b": 2}, {"a": 3, "c": 4}])
    lines = out.strip().splitlines()
    assert lines[0].split(",") == ["a", "b", "c"]
    assert lines[1].split(",") == ["1", "2", ""]
    assert lines[2].split(",") == ["3", "", "4"]


def test_markdown_table_truncates() -> None:
    rows = [{"a": i} for i in range(5)]
    md = as_markdown_table(rows, max_rows=3)
    assert "| a |" in md
    assert "+2 more rows truncated" in md


def test_page_envelope_includes_cursor() -> None:
    env = page_envelope([{"a": 1}], next_cursor="abc")
    assert env == {"rows": [{"a": 1}], "row_count": 1, "next_cursor": "abc"}


def test_safe_converts_value_error_to_structured_error() -> None:
    import asyncio

    from sac_mcp.client.errors import SACError
    from sac_mcp.tools._common import safe

    @safe
    async def bad_input_tool() -> dict:
        raise ValueError("Invalid aggregation operator 'median'")

    @safe
    async def sac_error_tool() -> dict:
        raise SACError("boom", status_code=400, code="Bad")

    out = asyncio.run(bad_input_tool())
    assert out["code"] == "invalid_input"
    assert "median" in out["error"]

    out = asyncio.run(sac_error_tool())
    assert out["status"] == 400
