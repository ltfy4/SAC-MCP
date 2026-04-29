"""Structured logging setup with secret redaction."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from sac_mcp.config import Settings

_REDACT_KEYS = {
    "authorization",
    "x-csrf-token",
    "set-cookie",
    "cookie",
    "client_secret",
    "sac_client_secret",
    "mcp_http_bearer",
    "access_token",
    "refresh_token",
}


def _redact(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for k in list(event_dict.keys()):
        if k.lower() in _REDACT_KEYS:
            event_dict[k] = "***"
    headers = event_dict.get("headers")
    if isinstance(headers, dict):
        event_dict["headers"] = {
            k: ("***" if k.lower() in _REDACT_KEYS else v) for k, v in headers.items()
        }
    return event_dict


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # stdio MCP servers MUST keep stdout clean for the protocol; log to stderr.
    logging.basicConfig(stream=sys.stderr, level=level, format="%(message)s")

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact,
    ]
    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
