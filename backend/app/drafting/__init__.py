"""Document drafting helpers for SAARTHI."""

from .docx_export import export_docx, export_docx_preview, load_template_text, template_path
from .generator import DraftingInputs, build_drafting_prompt, generate_document, validate_document_payload
from .prompt_builder import build_prompt
from .schema import (
    DOCUMENT_TYPES,
    DocumentDraft,
    DocumentSection,
    canonicalize_document_type,
    supported_document_types,
)

__all__ = [
    "DOCUMENT_TYPES",
    "DocumentDraft",
    "DocumentSection",
    "DraftingInputs",
    "build_drafting_prompt",
    "build_prompt",
    "canonicalize_document_type",
    "generate_document",
    "export_docx",
    "export_docx_preview",
    "load_template_text",
    "supported_document_types",
    "template_path",
    "validate_document_payload",
]
