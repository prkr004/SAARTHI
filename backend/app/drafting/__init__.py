"""Document drafting helpers for SAARTHI."""

from .docx_export import export_docx, export_docx_preview, load_template_text, template_path
from .generator import DraftingInputs, build_drafting_prompt, generate_document, validate_document_payload
from .prompt_builder import build_prompt
from .schema import (
    AdvisoryDraft,
    CircularDraft,
    DOCUMENT_TYPES,
    DraftDocument,
    PressReleaseDraft,
    canonicalize_document_type,
    draft_title,
    payload_schema_for_document_type,
    supported_document_types,
    validate_draft_payload,
)

__all__ = [
    "AdvisoryDraft",
    "CircularDraft",
    "DOCUMENT_TYPES",
    "DraftDocument",
    "PressReleaseDraft",
    "DraftingInputs",
    "build_drafting_prompt",
    "build_prompt",
    "canonicalize_document_type",
    "draft_title",
    "generate_document",
    "export_docx",
    "export_docx_preview",
    "load_template_text",
    "payload_schema_for_document_type",
    "supported_document_types",
    "template_path",
    "validate_draft_payload",
    "validate_document_payload",
]
