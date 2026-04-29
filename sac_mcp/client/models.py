"""Lightweight Pydantic DTOs used across tool modules.

We deliberately keep these minimal — most SAC payloads pass through as ``dict``
to avoid having to model every variation across SAC releases.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class SACEntity(BaseModel):
    """Base model with permissive extras (SAC ships extra fields between releases)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class StorySummary(SACEntity):
    storyId: str | None = None
    name: str | None = None
    description: str | None = None
    modifiedTime: str | None = None
    ownerId: str | None = None


class ModelSummary(SACEntity):
    namespace: str | None = None
    providerId: str | None = None
    name: str | None = None
    description: str | None = None


class JobInfo(SACEntity):
    jobID: str | None = None
    jobStatus: str | None = None
    importMethod: str | None = None
    creationTime: str | None = None
    error: Any | None = None
