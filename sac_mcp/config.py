"""Centralised configuration for the SAC MCP server.

Loaded once via :func:`get_settings` from environment variables (or `.env`).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Transport = Literal["stdio", "http"]
LogFormat = Literal["json", "console"]


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # SAC tenant
    sac_tenant_url: HttpUrl = Field(..., description="SAC tenant base URL.")
    sac_auth_url: HttpUrl = Field(..., description="OAuth authorization server URL.")
    sac_client_id: str = Field(..., min_length=1)
    sac_client_secret: SecretStr = Field(...)
    sac_oauth_scope: str | None = None

    # HTTP behaviour
    sac_request_timeout: float = 60.0
    sac_max_retries: int = 4
    sac_page_size: int = 1000
    sac_max_rps: float = 10.0

    # MCP transport
    mcp_transport: Transport = "stdio"
    mcp_http_host: str = "127.0.0.1"
    mcp_http_port: int = 8765
    mcp_http_bearer: SecretStr | None = None
    mcp_http_cors_origins: str = ""

    # Logging
    log_level: str = "INFO"
    log_format: LogFormat = "json"

    @field_validator("sac_tenant_url", "sac_auth_url", mode="after")
    @classmethod
    def _strip_trailing_slash(cls, v: HttpUrl) -> HttpUrl:
        # Pydantic HttpUrl already normalises, but re-parse to drop trailing slash for joins.
        s = str(v).rstrip("/")
        return HttpUrl(s)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.mcp_http_cors_origins.split(",") if o.strip()]

    @property
    def tenant_url_str(self) -> str:
        return str(self.sac_tenant_url).rstrip("/")

    @property
    def auth_url_str(self) -> str:
        return str(self.sac_auth_url).rstrip("/")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
