"""Strict drafting schemas for extraction-first document generation.

The LLM is restricted to returning structured data fields only. Final visual
layout is assembled programmatically via python-docx.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

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


def _normalize_required_text(value: object, field_name: str) -> str:
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty.")
    return cleaned


def _normalize_required_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be provided as a list of strings.")

    cleaned_items: list[str] = []
    seen: set[str] = set()
    for item in value:
        cleaned = " ".join(str(item or "").split())
        if not cleaned or cleaned in seen:
            continue
        cleaned_items.append(cleaned)
        seen.add(cleaned)

    if not cleaned_items:
        raise ValueError(f"{field_name} must contain at least one non-empty item.")
    return cleaned_items


class CircularDraft(BaseModel):
    """Strict extraction schema for circular documents."""

    model_config = ConfigDict(extra="forbid")

    document_type: Literal["circular"] = "circular"
    reference_number: str = Field(min_length=1, max_length=120)
    date: str = Field(min_length=1, max_length=80)
    addressee: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=300)
    highlights: list[str] = Field(default_factory=list)
    background_context: str = Field(min_length=1, max_length=5000)
    operational_directives: list[str] = Field(default_factory=list)
    compliance_warning: str = Field(min_length=1, max_length=1200)
    issuing_authority: str = Field(min_length=1, max_length=200)

    @field_validator(
        "reference_number",
        "date",
        "addressee",
        "subject",
        "background_context",
        "compliance_warning",
        "issuing_authority",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value: object, info) -> str:
        return _normalize_required_text(value, info.field_name.replace("_", " ").title())

    @field_validator("highlights", "operational_directives", mode="before")
    @classmethod
    def normalize_list_fields(cls, value: object, info) -> list[str]:
        return _normalize_required_list(value, info.field_name.replace("_", " ").title())


class AdvisoryDraft(BaseModel):
    """Strict extraction schema for advisory documents."""

    model_config = ConfigDict(extra="forbid")

    document_type: Literal["advisory"] = "advisory"
    priority_level: str = Field(min_length=1, max_length=40)
    date: str = Field(min_length=1, max_length=80)
    target_audience: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=300)
    issue_description: str = Field(min_length=1, max_length=5000)
    mitigating_actions: list[str] = Field(default_factory=list)
    reporting_mechanism: str = Field(min_length=1, max_length=2000)
    issuing_authority: str = Field(min_length=1, max_length=200)

    @field_validator(
        "priority_level",
        "date",
        "target_audience",
        "subject",
        "issue_description",
        "reporting_mechanism",
        "issuing_authority",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value: object, info) -> str:
        return _normalize_required_text(value, info.field_name.replace("_", " ").title())

    @field_validator("mitigating_actions", mode="before")
    @classmethod
    def normalize_list_fields(cls, value: object, info) -> list[str]:
        return _normalize_required_list(value, info.field_name.replace("_", " ").title())


class PressReleaseDraft(BaseModel):
    """Strict extraction schema for press release documents."""

    model_config = ConfigDict(extra="forbid")

    document_type: Literal["press_release"] = "press_release"
    date: str = Field(min_length=1, max_length=80)
    dateline: str = Field(min_length=1, max_length=120)
    headline: str = Field(min_length=1, max_length=300)
    lead_paragraph: str = Field(min_length=1, max_length=3000)
    body_paragraphs: list[str] = Field(default_factory=list)
    boilerplate_about: str = Field(min_length=1, max_length=3000)
    media_contact: str = Field(min_length=1, max_length=1000)

    @field_validator(
        "date",
        "dateline",
        "headline",
        "lead_paragraph",
        "boilerplate_about",
        "media_contact",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value: object, info) -> str:
        return _normalize_required_text(value, info.field_name.replace("_", " ").title())

    @field_validator("body_paragraphs", mode="before")
    @classmethod
    def normalize_list_fields(cls, value: object, info) -> list[str]:
        return _normalize_required_list(value, info.field_name.replace("_", " ").title())


DraftDocument = Annotated[
    CircularDraft | AdvisoryDraft | PressReleaseDraft,
    Field(discriminator="document_type"),
]

_DRAFT_DOCUMENT_ADAPTER = TypeAdapter(DraftDocument)


def draft_model_for_type(document_type: str) -> type[CircularDraft] | type[AdvisoryDraft] | type[PressReleaseDraft]:
    normalized = canonicalize_document_type(document_type)
    if normalized == "circular":
        return CircularDraft
    if normalized == "advisory":
        return AdvisoryDraft
    return PressReleaseDraft


def validate_draft_payload(payload: dict[str, Any], *, document_type: str | None = None) -> DraftDocument:
    if not isinstance(payload, dict):
        raise ValueError("Draft payload must be a JSON object.")

    candidate = dict(payload)
    if document_type is not None:
        candidate["document_type"] = canonicalize_document_type(document_type)
    elif "document_type" in candidate:
        candidate["document_type"] = canonicalize_document_type(str(candidate["document_type"]))
    else:
        raise ValueError("Draft payload must include a document_type.")

    model = draft_model_for_type(str(candidate["document_type"]))
    return model.model_validate(candidate)


def payload_schema_for_document_type(document_type: str) -> dict[str, Any]:
    normalized = canonicalize_document_type(document_type)
    if normalized == "circular":
        return {
            "document_type": "circular",
            "reference_number": "string",
            "date": "string",
            "addressee": "string",
            "subject": "string",
            "highlights": ["string"],
            "background_context": "string",
            "operational_directives": ["string"],
            "compliance_warning": "string",
            "issuing_authority": "string",
        }
    if normalized == "advisory":
        return {
            "document_type": "advisory",
            "priority_level": "string",
            "date": "string",
            "target_audience": "string",
            "subject": "string",
            "issue_description": "string",
            "mitigating_actions": ["string"],
            "reporting_mechanism": "string",
            "issuing_authority": "string",
        }
    return {
        "document_type": "press_release",
        "date": "string",
        "dateline": "string",
        "headline": "string",
        "lead_paragraph": "string",
        "body_paragraphs": ["string"],
        "boilerplate_about": "string",
        "media_contact": "string",
    }


def draft_title(draft: DraftDocument) -> str:
    if isinstance(draft, CircularDraft):
        return draft.subject
    if isinstance(draft, AdvisoryDraft):
        return draft.subject
    return draft.headline
