"""SAC error mapping.

SAC returns errors in a few different envelopes (OData v4 ``error.code/message``,
SCIM ``detail``, generic ``error_description``). This module normalises them into
:class:`SACError` so tools can return a single, LLM-friendly message.
"""

from __future__ import annotations

import contextlib
from typing import Any

import httpx


class SACError(Exception):
    """Normalised error from a SAC API call."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details

    def to_tool_message(self) -> str:
        parts: list[str] = []
        if self.status_code is not None:
            parts.append(f"HTTP {self.status_code}")
        if self.code:
            parts.append(self.code)
        parts.append(self.message)
        return " — ".join(parts)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.to_tool_message()


def from_response(response: httpx.Response) -> SACError:
    """Best-effort extract a structured SAC error from an HTTPX response."""

    status = response.status_code
    text = (response.text or "").strip()
    payload: Any = None
    with contextlib.suppress(ValueError):
        payload = response.json()

    code: str | None = None
    message: str | None = None

    if isinstance(payload, dict):
        # OData v4
        err = payload.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            message = err.get("message")
            if isinstance(message, dict):
                message = message.get("value")
        # SCIM
        if message is None:
            message = payload.get("detail") or payload.get("error_description") or payload.get(
                "message"
            )
        if code is None:
            # OAuth-style envelopes carry a string under "error"; SCIM carries
            # a status. Ignore dict values (an OData error object without a
            # "code" key) — stringifying those garbles to_tool_message().
            fallback = payload.get("error") or payload.get("status")
            if isinstance(fallback, (str, int)):
                code = str(fallback)

    if not message:
        message = text or response.reason_phrase or "SAC request failed"

    # Friendlier hints for common failure modes.
    hint = _hint_for_status(status, code, message)
    if hint:
        message = f"{message} ({hint})"

    return SACError(message=message, status_code=status, code=str(code) if code else None,
                    details=payload if payload is not None else text)


def _hint_for_status(status: int, code: str | None, message: str) -> str | None:
    if status == 401:
        return (
            "OAuth token rejected — verify SAC_CLIENT_ID/SAC_CLIENT_SECRET and OAuth scope, "
            "and that the App Integration record has the required roles"
        )
    if status == 403:
        if code and "csrf" in str(code).lower():
            return "CSRF token expired — will be re-fetched on retry"
        return "Permission denied — check the API role assigned to the OAuth client"
    if status == 404:
        return "Resource not found — verify model/story/job ID"
    if status == 429:
        return "Rate limited by SAC — backing off"
    return None
