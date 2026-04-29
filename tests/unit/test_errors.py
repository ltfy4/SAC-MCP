"""Tests for SAC error envelope parsing."""

from __future__ import annotations

import httpx

from sac_mcp.client.errors import from_response


def _resp(status: int, body: dict | str) -> httpx.Response:
    if isinstance(body, dict):
        return httpx.Response(status, json=body, request=httpx.Request("GET", "https://x"))
    return httpx.Response(status, text=body, request=httpx.Request("GET", "https://x"))


def test_odata_error_envelope() -> None:
    err = from_response(_resp(400, {"error": {"code": "BadRequest", "message": "boom"}}))
    assert err.status_code == 400
    assert err.code == "BadRequest"
    assert "boom" in err.message


def test_odata_message_can_be_object() -> None:
    err = from_response(
        _resp(500, {"error": {"code": "x", "message": {"value": "deep"}}})
    )
    assert "deep" in err.message


def test_scim_detail() -> None:
    err = from_response(_resp(404, {"detail": "user not found"}))
    assert "user not found" in err.message


def test_401_hint_is_added() -> None:
    err = from_response(_resp(401, "nope"))
    assert "OAuth token rejected" in err.message


def test_403_csrf_hint() -> None:
    err = from_response(_resp(403, {"error": {"code": "CSRF_TOKEN_BAD", "message": "bad"}}))
    assert "CSRF" in err.message or "csrf" in err.message
