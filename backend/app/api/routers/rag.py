"""RAG and temporal query endpoints for Phase 3."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from functools import lru_cache
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from models_config import AVAILABLE_MODELS, get_model_by_id, get_recommended_model
from predefined_responses import get_predefined_response
from query import ask_question, ask_temporal_question, format_source_label
from temporal.intent_detector import triage_query_intent

from backend.app.api.deps import get_current_user
from backend.app.core.config import get_settings
from backend.app.schemas.common import ApiEnvelope, ApiError
from backend.app.schemas.rag import AskRequest, AskTemporalRequest
from backend.app.services.execution import run_with_timeout

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rag"])
settings = get_settings()


def _empty_circular_linking_payload() -> dict:
    return {
        "related_circulars": [],
        "related_clauses": [],
    }


def _drafting_stub_answer() -> str:
    return (
        "Drafting request detected and routed to the drafting pipeline entrypoint. "
        "Full policy generation is not enabled in this phase yet. "
        "Please confirm institution type, policy scope, data retention period, and officer names "
        "to continue once drafting core is implemented."
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid4()))


def _json_response(status_code: int, envelope: ApiEnvelope) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


def _success(request: Request, data: dict) -> JSONResponse:
    return _json_response(
        status.HTTP_200_OK,
        ApiEnvelope(
            success=True,
            request_id=_request_id(request),
            timestamp=_now_iso(),
            data=data,
        ),
    )


def _failure(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
) -> JSONResponse:
    return _json_response(
        status_code,
        ApiEnvelope(
            success=False,
            request_id=_request_id(request),
            timestamp=_now_iso(),
            error=ApiError(code=code, message=message, details=details),
        ),
    )


def _error_details(reason: str) -> dict | None:
    if settings.expose_internal_error_details:
        return {"reason": reason}
    return None


@lru_cache(maxsize=64)
def _resolve_model_id_cached(model_id: str) -> str:
    model = get_model_by_id(model_id)
    if model is None:
        raise ValueError(f"Unsupported model id: {model_id}")
    return str(model["id"])


def _resolve_model_id(model_id: str | None) -> str:
    if model_id is None:
        return get_recommended_model()
    return _resolve_model_id_cached(model_id)


def _format_sources(sources: list[dict]) -> list[dict]:
    formatted: list[dict] = []
    label_cache: dict[tuple[str | None, int | None], tuple[str, str | None, int | None]] = {}

    for src in sources:
        metadata = src.get("metadata", {})
        source_key = metadata.get("source")
        page_key = metadata.get("page")
        cache_key = (str(source_key) if source_key is not None else None, int(page_key) if isinstance(page_key, int) else None)

        cached = label_cache.get(cache_key)
        if cached is None:
            cached = format_source_label(metadata)
            label_cache[cache_key] = cached

        doc_name, doc_link, page = cached
        formatted.append(
            {
                "document_name": doc_name,
                "document_link": doc_link,
                "page": page,
                "snippet": (src.get("content") or "")[:600],
                "metadata": metadata,
            }
        )
    return formatted


@router.get("/models", response_model=ApiEnvelope)
def list_models(request: Request, _: dict = Depends(get_current_user)) -> JSONResponse:
    payload = {
        "models": AVAILABLE_MODELS,
        "recommended_model": get_recommended_model(),
    }
    return _success(request, payload)


@router.post("/chat/ask", response_model=ApiEnvelope)
def ask(request: Request, payload: AskRequest, _: dict = Depends(get_current_user)) -> JSONResponse:
    started = time.perf_counter()
    model_call_started = None

    try:
        predefined = get_predefined_response(payload.question)
        if predefined:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return _success(
                request,
                {
                    "mode": "predefined",
                    "answer": predefined,
                    "sources": [],
                    "formatted_sources": [],
                    "circular_linking": _empty_circular_linking_payload(),
                    "metadata": {
                        "predefined": True,
                        "top_k": payload.top_k,
                        "elapsed_ms": elapsed_ms,
                    },
                },
            )

        model_id = _resolve_model_id(payload.model_id)
        model_call_started = time.perf_counter()
        result = run_with_timeout(
            ask_question,
            settings.rag_request_timeout_seconds,
            question=payload.question,
            k=payload.top_k,
            model_name=model_id,
        )

        sources = result.get("sources", [])
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return _success(
            request,
            {
                "mode": "qa",
                "answer": result.get("answer", ""),
                "sources": sources,
                "formatted_sources": _format_sources(sources),
                "circular_linking": result.get("circular_linking", _empty_circular_linking_payload()),
                "metadata": {
                    "predefined": False,
                    "top_k": payload.top_k,
                    "model_id": model_id,
                    "elapsed_ms": elapsed_ms,
                    "timings_ms": {
                        "model_call": int((time.perf_counter() - model_call_started) * 1000) if model_call_started else None,
                    },
                },
            },
        )
    except ValueError as exc:
        return _failure(request, status.HTTP_400_BAD_REQUEST, "validation_error", str(exc))
    except FileNotFoundError as exc:
        return _failure(
            request,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "vector_index_missing",
            "Vector index is not available.",
            _error_details(str(exc)),
        )
    except ConnectionError as exc:
        return _failure(
            request,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "model_unavailable",
            "Could not connect to local model service.",
            _error_details(str(exc)),
        )
    except TimeoutError as exc:
        return _failure(
            request,
            status.HTTP_504_GATEWAY_TIMEOUT,
            "request_timeout",
            "Model request timed out.",
            _error_details(str(exc)),
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error in /chat/ask")
        return _failure(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "Unexpected error while processing question.",
            _error_details(str(exc)),
        )


@router.post("/chat/ask-temporal", response_model=ApiEnvelope)
def ask_temporal(request: Request, payload: AskTemporalRequest, _: dict = Depends(get_current_user)) -> JSONResponse:
    started = time.perf_counter()
    model_call_started = None

    try:
        intent_class = triage_query_intent(payload.question)

        predefined = get_predefined_response(payload.question)
        if predefined:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return _success(
                request,
                {
                    "mode": "predefined",
                    "answer": predefined,
                    "sources": [],
                    "formatted_sources": [],
                    "circular_linking": _empty_circular_linking_payload(),
                    "temporal": {
                        "intent_detected": intent_class == "timeline_analysis",
                        "intent_class": intent_class,
                        "executed": False,
                        "fallback": False,
                        "single_version": False,
                    },
                    "metadata": {
                        "predefined": True,
                        "top_k": payload.top_k,
                        "comparison_method": payload.comparison_method,
                        "intent_class": intent_class,
                        "elapsed_ms": elapsed_ms,
                    },
                },
            )

        model_id = _resolve_model_id(payload.model_id)

        if intent_class == "fact_retrieval":
            model_call_started = time.perf_counter()
            result = run_with_timeout(
                ask_question,
                settings.rag_request_timeout_seconds,
                question=payload.question,
                k=payload.top_k,
                model_name=model_id,
            )
            sources = result.get("sources", [])
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return _success(
                request,
                {
                    "mode": "qa_fallback_non_temporal",
                    "answer": result.get("answer", ""),
                    "sources": sources,
                    "formatted_sources": _format_sources(sources),
                    "circular_linking": result.get("circular_linking", _empty_circular_linking_payload()),
                    "temporal": {
                        "intent_detected": False,
                        "intent_class": intent_class,
                        "executed": False,
                        "fallback": True,
                        "fallback_reason": "not_temporal_query",
                        "single_version": False,
                    },
                    "metadata": {
                        "predefined": False,
                        "top_k": payload.top_k,
                        "model_id": model_id,
                        "comparison_method": payload.comparison_method,
                        "intent_class": intent_class,
                        "elapsed_ms": elapsed_ms,
                        "timings_ms": {
                            "model_call": int((time.perf_counter() - model_call_started) * 1000)
                            if model_call_started
                            else None,
                        },
                    },
                },
            )

        if intent_class == "drafting_request":
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return _success(
                request,
                {
                    "mode": "drafting_stub",
                    "answer": _drafting_stub_answer(),
                    "sources": [],
                    "formatted_sources": [],
                    "circular_linking": _empty_circular_linking_payload(),
                    "temporal": {
                        "intent_detected": False,
                        "intent_class": intent_class,
                        "executed": False,
                        "fallback": True,
                        "fallback_reason": "drafting_request_stub",
                        "single_version": False,
                    },
                    "metadata": {
                        "predefined": False,
                        "top_k": payload.top_k,
                        "model_id": model_id,
                        "comparison_method": payload.comparison_method,
                        "intent_class": intent_class,
                        "elapsed_ms": elapsed_ms,
                        "drafting_stub": True,
                        "timings_ms": {
                            "model_call": None,
                        },
                    },
                },
            )

        model_call_started = time.perf_counter()
        result = run_with_timeout(
            ask_temporal_question,
            settings.temporal_request_timeout_seconds,
            question=payload.question,
            k=payload.top_k,
            model_name=model_id,
            comparison_method=payload.comparison_method,
        )

        fallback = bool(result.get("fallback", False))
        single_version = bool(result.get("single_version", False))
        sources = result.get("sources", []) if fallback else []

        if fallback:
            answer = result.get("answer", "")
            mode = "temporal_fallback"
        elif single_version:
            answer = (
                "Only one version of this document is currently indexed. "
                "Upload an earlier or newer version to enable change comparison."
            )
            mode = "temporal_single_version"
        else:
            comparison = result.get("comparison", {})
            answer = comparison.get("llm_summary", comparison.get("difflib_result", ""))
            mode = "temporal_comparison"

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return _success(
            request,
            {
                "mode": mode,
                "answer": answer,
                "sources": sources,
                "formatted_sources": _format_sources(sources),
                "circular_linking": result.get("circular_linking", _empty_circular_linking_payload()),
                "temporal": {
                    "intent_detected": True,
                    "intent_class": intent_class,
                    "executed": True,
                    "fallback": fallback,
                    "fallback_reason": result.get("fallback_reason"),
                    "single_version": single_version,
                    "document_title": result.get("document_title"),
                    "current_date": result.get("current_date"),
                    "previous_date": result.get("previous_date"),
                    "comparison": result.get("comparison") if not fallback and not single_version else None,
                },
                "metadata": {
                    "predefined": False,
                    "top_k": payload.top_k,
                    "model_id": model_id,
                    "comparison_method": payload.comparison_method,
                    "intent_class": intent_class,
                    "elapsed_ms": elapsed_ms,
                    "timings_ms": {
                        "model_call": int((time.perf_counter() - model_call_started) * 1000)
                        if model_call_started
                        else None,
                    },
                },
            },
        )
    except ValueError as exc:
        return _failure(request, status.HTTP_400_BAD_REQUEST, "validation_error", str(exc))
    except FileNotFoundError as exc:
        return _failure(
            request,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "vector_index_missing",
            "Vector index is not available.",
            _error_details(str(exc)),
        )
    except ConnectionError as exc:
        return _failure(
            request,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "model_unavailable",
            "Could not connect to local model service.",
            _error_details(str(exc)),
        )
    except TimeoutError as exc:
        return _failure(
            request,
            status.HTTP_504_GATEWAY_TIMEOUT,
            "request_timeout",
            "Temporal request timed out.",
            _error_details(str(exc)),
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error in /chat/ask-temporal")
        return _failure(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "Unexpected error while processing temporal query.",
            _error_details(str(exc)),
        )
