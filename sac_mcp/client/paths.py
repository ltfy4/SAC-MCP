"""URL building helpers.

Every identifier that ends up in a URL path (model, job, story, user, ...)
must go through :func:`seg`. httpx resolves ``..`` segments before sending,
so an unencoded ID such as ``"../../scim/Users/ALICE"`` passed to a tool
like ``cancel_job`` would otherwise turn into ``DELETE /api/v1/scim/Users/ALICE``.
Tool arguments come from an LLM, which may be steered by prompt injection,
so this is a real attack surface rather than a theoretical one.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

DES_ROOT = "/api/v1/dataexport/providers/sac"
DATA_IMPORT_ROOT = "/api/v1/dataimport"

# Characters left readable in query values. Space must become %20: SAC's file
# repository rejects the form-style "+" that httpx emits for params=.
_QUERY_SAFE = "$'(),:/@*!;"


def seg(value: object) -> str:
    """Percent-encode one path segment. Raises ValueError for unusable IDs."""

    text = str(value)
    if text in ("", ".", ".."):
        raise ValueError(f"Invalid identifier {text!r}")
    return quote(text, safe=":")


def des_path(model_id: str, entity: str = "") -> str:
    """Data Export Service path for a model; no entity = service document."""

    base = f"{DES_ROOT}/{seg(model_id)}/"
    return base + seg(entity) if entity else base


def encode_query(params: Mapping[str, Any]) -> str:
    """Encode query parameters OData-style (%20 for spaces, literal ``$``)."""

    parts: list[str] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        parts.append(f"{quote(str(key), safe='$')}={quote(str(value), safe=_QUERY_SAFE)}")
    return "&".join(parts)


def with_query(path: str, params: Mapping[str, Any] | None) -> str:
    """Append encoded ``params`` to ``path`` (which may already carry a query)."""

    query = encode_query(params) if params else ""
    if not query:
        return path
    return f"{path}{'&' if '?' in path else '?'}{query}"
