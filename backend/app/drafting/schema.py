"""Structured output schema for generated drafting documents.

The LLM is expected to return JSON that matches these models so the rest of
SAARTHI can render, validate, and export documents without relying on free-form
text.

Example payload::

    {
        "title": "KYC Update 2025",
        "document_type": "circular",
        "sections": [
            {"heading": "Subject", "content": "Updated KYC requirements..."}
        ],
        "references": ["RBI Master Direction on KYC"]
    }
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DOCUMENT_TYPES: tuple[str, ...] = ("circular", "press_release", "advisory")


def supported_document_types() -> tuple[str, ...]:
    """Return the document types currently supported by the drafting module."""

    return DOCUMENT_TYPES


def canonicalize_document_type(document_type: str) -> str:
    """Normalize a document type string into the canonical internal format."""

    cleaned = "_".join(str(document_type or "").strip().lower().replace("-", " ").split())
    if not cleaned:
        raise ValueError("Document type cannot be empty.")
    if cleaned not in DOCUMENT_TYPES:
        raise ValueError(
            f"Unsupported document type '{document_type}'. Supported types are: {', '.join(DOCUMENT_TYPES)}."
        )
    return cleaned


class DocumentSection(BaseModel):
    """Single section within a generated drafting document."""

    model_config = ConfigDict(extra="forbid")

    heading: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20000)

    @field_validator("heading", "content", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            raise ValueError("Section fields cannot be empty.")
        return cleaned


class DocumentDraft(BaseModel):
    """Structured JSON output returned by the drafting LLM."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    document_type: str = Field(min_length=1, max_length=50)
    sections: list[DocumentSection] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)

    _canonical_document_type: ClassVar[set[str]] = set(DOCUMENT_TYPES)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> str:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            raise ValueError("Title cannot be empty.")
        return cleaned

    @field_validator("document_type", mode="before")
    @classmethod
    def normalize_document_type(cls, value: object) -> str:
        return canonicalize_document_type(str(value or ""))

    @field_validator("references", mode="before")
    @classmethod
    def normalize_references(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("References must be provided as a list of strings.")

        cleaned_references: list[str] = []
        seen: set[str] = set()
        for item in value:
            cleaned = " ".join(str(item or "").split())
            if not cleaned or cleaned in seen:
                continue
            cleaned_references.append(cleaned)
            seen.add(cleaned)
        return cleaned_references

    @model_validator(mode="after")
    def ensure_sections_present(self) -> "DocumentDraft":
        if not self.sections:
            raise ValueError("At least one section is required in the generated document.")
        return self
