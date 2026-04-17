"""Prompt construction utilities for document drafting.

This module turns retrieved RAG context, optional temporal changes, and user
inputs into a compact prompt that asks the LLM for JSON-only output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.drafting.schema import canonicalize_document_type

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
    """Build a strict prompt that asks the LLM to return JSON only."""

    normalized_type = canonicalize_document_type(document_type)
    template_text = load_template_text(normalized_type)
    payload_schema = {
        "title": "string",
        "document_type": normalized_type,
        "sections": [
            {"heading": "string", "content": "string"},
        ],
        "references": ["string"],
    }

    return (
        "You are SAARTHI, a banking regulatory drafting assistant.\n"
        "Use ONLY the supplied context. Do not invent facts, clauses, dates, or references.\n"
        "Write in a formal BFSI tone suitable for internal banking communication.\n"
        "Return valid JSON only. Do not wrap the response in markdown, code fences, or prose.\n"
        "The response must be a single JSON object and must match the schema exactly.\n\n"
        f"Document type: {normalized_type}\n\n"
        "Template guidance:\n"
        f"{template_text}\n\n"
        "Retrieved regulatory context:\n"
        f"{_stringify_block(rag_content)}\n\n"
        "Temporal changes, if any:\n"
        f"{_stringify_block(temporal_changes)}\n\n"
        "User input:\n"
        f"{_stringify_block(user_input)}\n\n"
        "Output schema requirements:\n"
        f"{json.dumps(payload_schema, ensure_ascii=True, indent=2)}\n\n"
        "Rules:\n"
        "1. Output must contain only the keys in the schema.\n"
        "2. 'sections' must be a non-empty array of objects with 'heading' and 'content'.\n"
        "3. 'references' must list only references that are grounded in the provided context.\n"
        "4. Keep the response concise, structured, and operational.\n"
    )
