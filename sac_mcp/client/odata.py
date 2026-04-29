"""Tiny OData v4 query builder used by the Data Export and Resources tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ODataQuery:
    """Builder for the subset of OData v4 we need."""

    filter: str | None = None
    select: list[str] = field(default_factory=list)
    orderby: list[str] = field(default_factory=list)
    top: int | None = None
    skip: int | None = None
    expand: list[str] = field(default_factory=list)
    count: bool = False
    extra: dict[str, str] = field(default_factory=dict)

    def to_params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        if self.filter:
            params["$filter"] = self.filter
        if self.select:
            params["$select"] = ",".join(self.select)
        if self.orderby:
            params["$orderby"] = ",".join(self.orderby)
        if self.top is not None:
            params["$top"] = str(self.top)
        if self.skip is not None:
            params["$skip"] = str(self.skip)
        if self.expand:
            params["$expand"] = ",".join(self.expand)
        if self.count:
            params["$count"] = "true"
        params.update(self.extra)
        return params


def quote_odata_string(value: str) -> str:
    """Escape a value for use inside an OData ``$filter`` string literal."""

    return "'" + value.replace("'", "''") + "'"


def eq(field_name: str, value: Any) -> str:
    return f"{field_name} eq {_format(value)}"


def ne(field_name: str, value: Any) -> str:
    return f"{field_name} ne {_format(value)}"


def gt(field_name: str, value: Any) -> str:
    return f"{field_name} gt {_format(value)}"


def lt(field_name: str, value: Any) -> str:
    return f"{field_name} lt {_format(value)}"


def contains(field_name: str, value: str) -> str:
    return f"contains({field_name},{quote_odata_string(value)})"


def starts_with(field_name: str, value: str) -> str:
    return f"startswith({field_name},{quote_odata_string(value)})"


def and_(*clauses: str) -> str:
    parts = [c for c in clauses if c]
    return " and ".join(f"({c})" for c in parts) if len(parts) > 1 else (parts[0] if parts else "")


def or_(*clauses: str) -> str:
    parts = [c for c in clauses if c]
    return " or ".join(f"({c})" for c in parts) if len(parts) > 1 else (parts[0] if parts else "")


def _format(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return quote_odata_string(str(value))
