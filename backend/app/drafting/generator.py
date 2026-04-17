"""High-level orchestration helpers for drafting prompts and payloads.

This module assembles the prompt, retrieves supporting regulatory context using
the existing RAG utilities, optionally adds temporal comparison context, and
parses the LLM response into the structured drafting schema.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from backend.app.core.sanitization import sanitize_text
from backend.app.drafting.prompt_builder import build_prompt
from backend.app.drafting.schema import DocumentDraft
from query import DEFAULT_OLLAMA_MODEL, ask_temporal_question, format_source_label, get_llm, load_vectorstore, retrieve_relevant_docs
from temporal.intent_detector import detect_temporal_intent

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


@dataclass(slots=True)
class DraftingInputs:
    """Container for the inputs required to draft a regulated document."""

    document_type: str
    user_input: dict[str, Any] = field(default_factory=dict)
    rag_content: Any | None = None
    temporal_changes: Any | None = None


def _normalize_user_input(user_input: Any) -> dict[str, Any]:
    if user_input is None:
        return {}
    if isinstance(user_input, dict):
        normalized: dict[str, Any] = {}
        for key, value in user_input.items():
            if isinstance(value, str):
                normalized[key] = sanitize_text(value, collapse_whitespace=True)
            else:
                normalized[key] = value

        if "query" not in normalized:
            for key in ("topic", "question", "prompt", "subject"):
                candidate = normalized.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    normalized["query"] = candidate
                    break
        return normalized

    return {"query": sanitize_text(user_input, collapse_whitespace=True)}


def _extract_query_text(user_input: dict[str, Any]) -> str:
    for key in ("query", "topic", "question", "prompt", "subject"):
        value = user_input.get(key)
        if isinstance(value, str):
            cleaned = sanitize_text(value, collapse_whitespace=True)
            if cleaned:
                return cleaned
    return ""


def _format_retrieved_context(documents: list[Any]) -> dict[str, Any]:
    formatted_documents: list[dict[str, Any]] = []
    for doc in documents:
        metadata = dict(getattr(doc, "metadata", {}) or {})
        source_label, source_url, page = format_source_label(metadata)
        formatted_documents.append(
            {
                "content": getattr(doc, "page_content", ""),
                "metadata": metadata,
                "source_label": source_label,
                "source_url": source_url,
                "page": page,
            }
        )

    return {
        "document_count": len(formatted_documents),
        "documents": formatted_documents,
    }


def _extract_json_candidate(raw_response: object) -> str:
    if raw_response is None:
        raise ValueError("The model returned no response.")

    if hasattr(raw_response, "content"):
        raw_text = str(getattr(raw_response, "content"))
    else:
        raw_text = str(raw_response)

    raw_text = raw_text.strip()
    if not raw_text:
        raise ValueError("The model returned an empty response.")

    fenced = _JSON_FENCE_RE.search(raw_text)
    if fenced:
        return fenced.group(1).strip()

    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw_text[start : end + 1].strip()

    return raw_text


def _parse_document_payload(raw_response: object, document_type: str) -> DocumentDraft:
    json_candidate = _extract_json_candidate(raw_response)

    try:
        payload = json.loads(json_candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("The model did not return valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ValueError("The model response must be a JSON object.")

    payload["document_type"] = document_type
    return DocumentDraft.model_validate(payload)


def build_drafting_prompt(inputs: DraftingInputs) -> str:
    """Build the model prompt for a drafting request."""

    return build_prompt(
        document_type=inputs.document_type,
        rag_content=inputs.rag_content,
        temporal_changes=inputs.temporal_changes,
        user_input=inputs.user_input,
    )


def validate_document_payload(payload: dict[str, Any]) -> DocumentDraft:
    """Validate a model response against the structured drafting schema."""

    return DocumentDraft.model_validate(payload)


def generate_document(
    document_type: str,
    user_input: dict[str, Any] | Any,
    *,
    model_name: str = DEFAULT_OLLAMA_MODEL,
    top_k: int = 4,
    comparison_method: str = "both",
) -> DocumentDraft:
    """Generate a structured drafting document from RAG and temporal context."""

    normalized_document_type = DocumentDraft.model_validate(
        {
            "title": "Draft",
            "document_type": document_type,
            "sections": [{"heading": "Temp", "content": "Temp"}],
            "references": [],
        }
    ).document_type
    normalized_input = _normalize_user_input(user_input)
    query_text = _extract_query_text(normalized_input)

    if not query_text:
        raise ValueError("A topic or query is required to generate a document.")

    logger.info(
        "Starting drafting request",
        extra={
            "document_type": normalized_document_type,
            "query": query_text,
            "model_name": model_name,
            "top_k": top_k,
        },
    )

    try:
        vectorstore = load_vectorstore()
        documents = retrieve_relevant_docs(vectorstore, query_text, k=top_k)
    except Exception as exc:
        logger.exception("Drafting retrieval failed")
        raise RuntimeError("Failed to retrieve regulatory context for drafting.") from exc

    if not documents:
        raise RuntimeError("No relevant regulatory content was found for the requested document.")

    rag_content = _format_retrieved_context(documents)
    temporal_changes: Any = None

    if detect_temporal_intent(query_text):
        try:
            temporal_result = ask_temporal_question(
                query_text,
                k=top_k,
                model_name=model_name,
                comparison_method=comparison_method,
            )
            temporal_changes = temporal_result.get("comparison") or temporal_result
        except Exception as exc:
            logger.warning("Temporal comparison failed for drafting request: %s", exc)
            temporal_changes = {"error": "Temporal comparison could not be completed."}

    prompt = build_prompt(
        document_type=normalized_document_type,
        rag_content=rag_content,
        temporal_changes=temporal_changes,
        user_input=normalized_input,
    )

    try:
        llm = get_llm(model_name=model_name)
        raw_response = llm.invoke(prompt)
    except Exception as exc:
        logger.exception("Drafting model call failed")
        raise RuntimeError("The document drafting model could not be reached.") from exc

    try:
        document = _parse_document_payload(raw_response, normalized_document_type)
    except Exception as exc:
        logger.exception("Drafting model returned an invalid payload")
        raise RuntimeError("The model returned an invalid structured document.") from exc

    logger.info(
        "Drafting request completed",
        extra={"document_type": normalized_document_type, "section_count": len(document.sections)},
    )
    return document
