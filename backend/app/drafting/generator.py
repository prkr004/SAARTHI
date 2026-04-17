"""High-level orchestration helpers for strict drafting extraction payloads.

This module assembles the extraction prompt, retrieves supporting regulatory
context, calls the model, validates the returned JSON against strict typed
schemas, and returns document-type-specific payloads for programmatic assembly.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

try:
    from requests import exceptions as requests_exceptions
except Exception:  # pragma: no cover - requests is expected, but keep module import-safe
    requests_exceptions = None

from backend.app.core.sanitization import sanitize_text
from backend.app.drafting.prompt_builder import build_prompt
from backend.app.drafting.schema import (
    AdvisoryDraft,
    CircularDraft,
    DraftDocument,
    PressReleaseDraft,
    canonicalize_document_type,
    validate_draft_payload,
)
from query import DEFAULT_OLLAMA_MODEL, ask_temporal_question, format_source_label, get_llm, load_vectorstore, retrieve_relevant_docs
from temporal.intent_detector import detect_temporal_intent

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_FALLBACK_CONTEXT_SNIPPET_LIMIT = 320


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc

    while current is not None and id(current) not in seen:
        chain.append(current)
        seen.add(id(current))
        current = current.__cause__ or current.__context__

    return chain


def _is_model_service_unavailable(exc: BaseException) -> bool:
    connection_types: tuple[type[BaseException], ...] = (ConnectionRefusedError, TimeoutError)
    if requests_exceptions is not None:
        connection_types = (
            *connection_types,
            requests_exceptions.ConnectionError,
            requests_exceptions.Timeout,
        )

    for item in _iter_exception_chain(exc):
        if isinstance(item, connection_types):
            return True

        message = str(item).lower()
        if "localhost" in message and "11434" in message:
            return True
        if "failed to establish a new connection" in message:
            return True
        if "max retries exceeded" in message and "api/generate" in message:
            return True

    return False


def _truncate_context_snippet(value: str, *, limit: int = _FALLBACK_CONTEXT_SNIPPET_LIMIT) -> str:
    cleaned = sanitize_text(value or "", collapse_whitespace=True)
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3].rstrip()}..."


def _fallback_actions(document_type: str, audience: str) -> list[str]:
    common = [
        "Validate obligations against the latest internal policy register and approved circular repository.",
        "Confirm ownership and implementation timelines with Compliance, Legal, and Operations teams.",
        f"Circulate the final signed document to the target audience ({audience}) with acknowledgement tracking.",
    ]

    if document_type == "press_release":
        return [
            "Complete legal and public communication review before external publication.",
            "Align release timing with regulator communication and media disclosure windows.",
            *common,
        ]

    if document_type == "advisory":
        return [
            "Activate control checks on a priority basis and assign accountable risk owners.",
            "Escalate unresolved control gaps to the central compliance office without delay.",
            *common,
        ]

    return [
        "Map each requirement to branch-level control checkpoints and operational SOP updates.",
        "Track compliance closure through internal audit-ready evidence and completion logs.",
        *common,
    ]


def _today_corporate_date() -> str:
    return datetime.now().strftime("%d %B %Y")


def _collect_context_summaries(rag_content: dict[str, Any]) -> tuple[list[str], list[str]]:
    references: list[str] = []
    summaries: list[str] = []
    seen_references: set[str] = set()

    documents = rag_content.get("documents", []) if isinstance(rag_content, dict) else []
    if not isinstance(documents, list):
        return references, summaries

    for item in documents[:4]:
        if not isinstance(item, dict):
            continue

        source_label = str(item.get("source_label") or "Retrieved source").strip() or "Retrieved source"
        page = item.get("page")
        page_suffix = f" (p. {page})" if isinstance(page, int) else ""
        reference = f"{source_label}{page_suffix}"
        if reference not in seen_references:
            references.append(reference)
            seen_references.add(reference)

        snippet = _truncate_context_snippet(str(item.get("content", "")))
        if snippet:
            summaries.append(f"{reference}: {snippet}")

    return references, summaries


def _build_fallback_document(
    *,
    document_type: str,
    query_text: str,
    user_input: dict[str, Any],
    rag_content: dict[str, Any],
    reason: str,
) -> DraftDocument:
    audience = sanitize_text(user_input.get("audience", "internal"), collapse_whitespace=True) or "internal"
    references, summaries = _collect_context_summaries(rag_content)

    if not summaries:
        summaries = ["Retrieved regulatory context is available but could not be summarized automatically."]

    if document_type == "circular":
        return CircularDraft.model_validate(
            {
                "document_type": "circular",
                "reference_number": "HO Circular No. AUTO/2026-27/001",
                "date": _today_corporate_date(),
                "addressee": f"All {audience} units and branch operations",
                "subject": f"Operational circular on {query_text}",
                "highlights": summaries[:3],
                "background_context": "; ".join(summaries[:2]),
                "operational_directives": _fallback_actions("circular", audience),
                "compliance_warning": (
                    "Branches are advised to ensure strict compliance with immediate effect. "
                    f"Model fallback reason: {reason}"
                ),
                "issuing_authority": "Chief General Manager, Compliance Department",
            }
        )

    if document_type == "advisory":
        return AdvisoryDraft.model_validate(
            {
                "document_type": "advisory",
                "priority_level": "URGENT",
                "date": _today_corporate_date(),
                "target_audience": f"All {audience} control and operations teams",
                "subject": f"Compliance advisory on {query_text}",
                "issue_description": "; ".join(summaries[:2]),
                "mitigating_actions": _fallback_actions("advisory", audience),
                "reporting_mechanism": (
                    "Submit compliance confirmation to the central compliance cell by close of business on the "
                    "next working day, including exception logs and remediation status."
                ),
                "issuing_authority": "Chief Risk Officer",
            }
        )

    return PressReleaseDraft.model_validate(
        {
            "document_type": "press_release",
            "date": _today_corporate_date(),
            "dateline": "Mumbai, India",
            "headline": f"Regulatory update on {query_text}",
            "lead_paragraph": summaries[0],
            "body_paragraphs": summaries[:3],
            "boilerplate_about": (
                "The institution remains committed to responsible banking, transparent disclosures, and "
                "full compliance with applicable regulatory guidance."
            ),
            "media_contact": "Public Relations Desk | mediarelations@bank.example | +91-22-0000-0000",
        }
    )


@dataclass(slots=True)
class DraftingInputs:
    """Container for inputs required to draft a regulated document."""

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


def _parse_document_payload(raw_response: object, document_type: str) -> DraftDocument:
    json_candidate = _extract_json_candidate(raw_response)

    try:
        payload = json.loads(json_candidate)
    except json.JSONDecodeError as exc:
        raise ValueError("The model did not return valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ValueError("The model response must be a JSON object.")

    return validate_draft_payload(payload, document_type=document_type)


def build_drafting_prompt(inputs: DraftingInputs) -> str:
    """Build the model prompt for a drafting request."""

    return build_prompt(
        document_type=inputs.document_type,
        rag_content=inputs.rag_content,
        temporal_changes=inputs.temporal_changes,
        user_input=inputs.user_input,
    )


def validate_document_payload(payload: dict[str, Any], *, document_type: str | None = None) -> DraftDocument:
    """Validate a model response against strict drafting schema models."""

    return validate_draft_payload(payload, document_type=document_type)


def generate_document(
    document_type: str,
    user_input: dict[str, Any] | Any,
    *,
    model_name: str = DEFAULT_OLLAMA_MODEL,
    top_k: int = 4,
    comparison_method: str = "both",
) -> DraftDocument:
    """Generate strict extraction payload for drafting assembly."""

    normalized_document_type = canonicalize_document_type(document_type)
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
        if _is_model_service_unavailable(exc):
            logger.warning("Drafting model unavailable; returning strict fallback payload")
            return _build_fallback_document(
                document_type=normalized_document_type,
                query_text=query_text,
                user_input=normalized_input,
                rag_content=rag_content,
                reason="Could not connect to the local model service (Ollama).",
            )

        logger.exception("Drafting model call failed")
        raise RuntimeError("The document drafting model could not be reached.") from exc

    try:
        document = _parse_document_payload(raw_response, normalized_document_type)
    except Exception as exc:
        logger.warning("Drafting model returned invalid structured payload; returning strict fallback payload")
        return _build_fallback_document(
            document_type=normalized_document_type,
            query_text=query_text,
            user_input=normalized_input,
            rag_content=rag_content,
            reason="Model output was not valid for strict schema validation.",
        )

    logger.info(
        "Drafting request completed",
        extra={
            "document_type": normalized_document_type,
            "payload_model": type(document).__name__,
        },
    )
    return document
