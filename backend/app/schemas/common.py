"""Shared API response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiMessage(BaseModel):
    """Simple message envelope for success operations."""

    message: str


class HealthStatus(BaseModel):
    """Health endpoint payload."""

    status: str
    service: str
    version: str
    details: dict[str, Any] | None = None


class ApiError(BaseModel):
    """Structured error payload used by envelope responses."""

    code: str
    message: str
    details: dict[str, Any] | None = None


class ApiEnvelope(BaseModel):
    """Consistent response envelope for frontend-facing APIs."""

    success: bool
    request_id: str
    timestamp: str
    data: dict[str, Any] | None = None
    error: ApiError | None = None
