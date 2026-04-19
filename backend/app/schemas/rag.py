"""Schemas for model listing and RAG/temporal query endpoints."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from backend.app.core.sanitization import sanitize_text


_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9:._-]{1,120}$")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    model_id: str | None = Field(default=None, max_length=120)
    top_k: int = Field(default=4, ge=1, le=20)

    @field_validator("question", mode="before")
    @classmethod
    def normalize_question(cls, value: object) -> str:
        cleaned = sanitize_text(value, collapse_whitespace=True)
        if not cleaned:
            raise ValueError("Question cannot be empty.")
        return cleaned

    @field_validator("model_id", mode="before")
    @classmethod
    def normalize_model_id(cls, value: object) -> str | None:
        if value is None:
            return None

        cleaned = sanitize_text(value, collapse_whitespace=True)
        if not cleaned:
            return None
        if not _MODEL_ID_RE.match(cleaned):
            raise ValueError("Unsupported model id format.")
        return cleaned


class AskTemporalRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    model_id: str | None = Field(default=None, max_length=120)
    top_k: int = Field(default=4, ge=1, le=20)
    comparison_method: str = Field(default="both", pattern=r"^(difflib|llm|both)$")
    mode: str | None = Field(default=None, pattern=r"^(fast|thinking)$")

    @field_validator("question", mode="before")
    @classmethod
    def normalize_question(cls, value: object) -> str:
        cleaned = sanitize_text(value, collapse_whitespace=True)
        if not cleaned:
            raise ValueError("Question cannot be empty.")
        return cleaned

    @field_validator("model_id", mode="before")
    @classmethod
    def normalize_model_id(cls, value: object) -> str | None:
        if value is None:
            return None

        cleaned = sanitize_text(value, collapse_whitespace=True)
        if not cleaned:
            return None
        if not _MODEL_ID_RE.match(cleaned):
            raise ValueError("Unsupported model id format.")
        return cleaned

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: object) -> str | None:
        if value is None:
            return None

        cleaned = sanitize_text(value, collapse_whitespace=True).lower()
        if not cleaned:
            return None
        return cleaned
