"""Schemas for the document drafting endpoint."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from backend.app.core.sanitization import sanitize_text
from backend.app.drafting.schema import canonicalize_document_type

_AUDIENCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,60}$")


class GenerateDocumentRequest(BaseModel):
    document_type: str = Field(min_length=1, max_length=50)
    query: str = Field(min_length=1, max_length=4000)
    audience: str = Field(default="internal", min_length=1, max_length=80)

    @field_validator("document_type", mode="before")
    @classmethod
    def normalize_document_type(cls, value: object) -> str:
        return canonicalize_document_type(str(value or ""))

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: object) -> str:
        cleaned = sanitize_text(value, collapse_whitespace=True)
        if not cleaned:
            raise ValueError("Query cannot be empty.")
        return cleaned

    @field_validator("audience", mode="before")
    @classmethod
    def normalize_audience(cls, value: object) -> str:
        cleaned = sanitize_text(value, collapse_whitespace=True)
        if not cleaned:
            return "internal"
        if not _AUDIENCE_RE.match(cleaned):
            raise ValueError("Audience contains unsupported characters.")
        return cleaned
