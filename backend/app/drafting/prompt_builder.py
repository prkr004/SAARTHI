"""Prompt construction utilities for document drafting.

This module turns retrieved RAG context, optional temporal changes, and user
inputs into a compact prompt that asks the LLM for JSON-only output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.drafting.schema import canonicalize_document_type, payload_schema_for_document_type

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def template_path(document_type: str) -> Path:
    """Return the template file path for a supported document type."""

    normalized = canonicalize_document_type(document_type)
    return _TEMPLATE_DIR / f"{normalized}.txt"


def load_template_text(document_type: str) -> str:
    """Load the plain-text template for the requested document type."""

    path = template_path(document_type)
    if not path.exists():
        raise FileNotFoundError(f"Template file not found for document type '{document_type}'.")
    return path.read_text(encoding="utf-8")


def _stringify_block(value: Any) -> str:
    if value is None:
        return "(none)"
    if isinstance(value, str):
        text = " ".join(value.split())
        return text or "(none)"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=True, indent=2, default=str)
    return str(value)


def build_prompt(
    document_type: str,
    rag_content: Any,
    temporal_changes: Any,
    user_input: Any,
) -> str:
    """Build a strict prompt that asks the LLM to return extraction data only."""

    normalized_type = canonicalize_document_type(document_type)
    template_text = load_template_text(normalized_type)
    payload_schema = payload_schema_for_document_type(normalized_type)

    return (
        "You are a backend data extractor for banking regulations.\n"
        "Your ONLY job is to analyze the retrieved context and populate the provided JSON schema.\n"
        "DO NOT include markdown formatting, newlines (\\n), or bullet points in the strings.\n"
        "We will handle visual formatting programmatically.\n"
        "Output must be 100% production-ready and instantly publishable with zero human review.\n"
        "Use precise Indian banking phraseology such as 'It has been decided to...', 'Branches are advised to ensure strict compliance...', and 'Please refer to our earlier master direction...'.\n"
        "Maintain authoritative, objective, and legally sound BFSI language.\n"
        "Hallucinations of regulatory rules are strictly forbidden; use only the supplied context with factual fidelity.\n"
        "Return valid JSON only, as one object, matching the schema exactly.\n\n"
        f"Document type: {normalized_type}\n\n"
        "Template semantics (for section intent only, not formatting replication):\n"
        f"{template_text}\n\n"
        "Retrieved regulatory context:\n"
        f"{_stringify_block(rag_content)}\n\n"
        "Temporal changes, if any:\n"
        f"{_stringify_block(temporal_changes)}\n\n"
        "User input:\n"
        f"{_stringify_block(user_input)}\n\n"
        "Output schema requirements:\n"
        f"{json.dumps(payload_schema, ensure_ascii=True, indent=2)}\n\n"
        "Extraction rules:\n"
        "1. Include only keys defined in the schema. No extra keys.\n"
        "2. Every string field must be a single-line value with no embedded newline characters.\n"
        "3. Do not prefix strings with numbering, dashes, or bullets.\n"
        "4. For list fields (e.g., highlights, operational_directives, mitigating_actions, body_paragraphs), generate distinct, non-overlapping, actionable items.\n"
        "5. If context omits a reference number for circulars, generate a realistic placeholder such as 'RBI/2026-27/...' or 'HO Circular No. ...'.\n"
        "6. If context omits date values, generate realistic Indian corporate date strings.\n"
        "7. Ensure all values are publication-grade and directly consumable by backend assembly code.\n"
    )
