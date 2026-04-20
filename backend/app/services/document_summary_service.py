"""Asynchronous document summary worker for registry summaries."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

import chat_store

from backend.app.core.config import get_settings
from backend.app.services.rag_cache_service import refresh_rag_caches

logger = logging.getLogger(__name__)

_WORKER_THREAD: threading.Thread | None = None
_WORKER_STOP_EVENT = threading.Event()
_WORKER_WAKE_EVENT = threading.Event()
_WORKER_GUARD = threading.Lock()
_SUMMARY_PROCESS_LOCK = threading.Lock()


@dataclass
class DocumentSummaryRunStats:
    claimed_documents: int = 0
    completed_documents: int = 0
    failed_documents: int = 0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split()).strip()
    return cleaned or None


def _normalize_exception_message(exc: Exception, *, max_length: int = 800) -> str:
    raw = _normalize_text(str(exc)) or exc.__class__.__name__
    if len(raw) <= max_length:
        return raw
    return f"{raw[: max_length - 3]}..."


def _truncate_sentence(value: str, *, max_length: int = 220) -> str:
    cleaned = " ".join(value.split()).strip()
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 3]}..."


def _coerce_int(value: object, default: int = 0) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return default


def _metadata_map(document: Mapping[str, object]) -> dict:
    metadata = document.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    return {}


def generate_document_summaries(document: Mapping[str, object]) -> tuple[str, str]:
    """Generate one-line and paragraph summaries from registry metadata."""

    metadata = _metadata_map(document)
    if bool(metadata.get("force_summary_failure")):
        raise RuntimeError("Forced summary failure via document metadata.")

    title = _normalize_text(document.get("document_title")) or "Untitled regulatory document"
    regulator = _normalize_text(document.get("regulator")) or "Unknown regulator"
    version_date = _normalize_text(document.get("version_date"))
    effective_date = _normalize_text(document.get("effective_date"))
    document_status = (_normalize_text(document.get("document_status")) or "Active").lower()
    source = _normalize_text(document.get("source")) or "unknown source"
    chunk_count = _coerce_int(document.get("chunk_count"), default=0)

    version_phrase = f"version {version_date}" if version_date else "undated version"
    effective_phrase = (
        f"effective from {effective_date}" if effective_date else "with no recorded effective date"
    )
    chunk_phrase = "1 indexed section" if chunk_count == 1 else f"{chunk_count} indexed sections"

    one_liner = _truncate_sentence(
        f"{title} ({regulator}, {version_phrase}) provides {document_status} guidance across {chunk_phrase}."
    )

    paragraph_parts = [
        f"{title} is cataloged under {regulator} as a {document_status} document, {version_phrase}, and is {effective_phrase}.",
        f"The document currently maps to {chunk_phrase} in the retrieval index and is sourced from {source}.",
    ]

    source_candidates = metadata.get("source_candidates")
    if isinstance(source_candidates, list) and source_candidates:
        normalized_candidates = [
            candidate for candidate in (_normalize_text(item) for item in source_candidates) if candidate
        ]
        if normalized_candidates:
            paragraph_parts.append(
                f"Indexed source variants include {', '.join(normalized_candidates[:3])}."
            )

    paragraph = _truncate_sentence(" ".join(paragraph_parts), max_length=600)
    return one_liner, paragraph


def _run_document_summarization_internal(
    *,
    batch_size: int,
    include_failed: bool,
    retry_after_seconds: int,
) -> DocumentSummaryRunStats:
    stats = DocumentSummaryRunStats()

    for _ in range(max(1, int(batch_size))):
        document = chat_store.claim_next_document_for_summary(
            include_failed=bool(include_failed),
            retry_after_seconds=max(0, int(retry_after_seconds)),
            audit_reason="Summary worker claimed document for generation.",
        )
        if document is None:
            break

        stats.claimed_documents += 1
        document_id = int(document["id"])

        try:
            one_liner, paragraph = generate_document_summaries(document)
            updated = chat_store.update_document_summary(
                document_id,
                summary_status=chat_store.DOCUMENT_SUMMARY_STATUS_COMPLETED,
                summary_one_liner=one_liner,
                summary_short=paragraph,
                summary_error=None,
                audit_reason="Summary worker generated document summary.",
            )
            if updated:
                stats.completed_documents += 1
            else:
                logger.warning("Summary completion skipped because document became unavailable.", extra={"document_id": document_id})
        except Exception as exc:  # pragma: no cover - defensive branch
            error_message = _normalize_exception_message(exc)
            chat_store.update_document_summary(
                document_id,
                summary_status=chat_store.DOCUMENT_SUMMARY_STATUS_FAILED,
                summary_error=error_message,
                audit_reason="Summary worker failed; document retained for retry.",
            )
            stats.failed_documents += 1

    return stats


def run_document_summarization_once(
    *,
    batch_size: int | None = None,
    include_failed: bool | None = None,
    retry_after_seconds: int | None = None,
) -> DocumentSummaryRunStats:
    """Process one summary batch and persist status transitions for each document."""

    settings = get_settings()
    safe_batch_size = max(1, int(batch_size or settings.document_summary_batch_size))
    safe_include_failed = (
        settings.document_summary_retry_failed_enabled
        if include_failed is None
        else bool(include_failed)
    )
    safe_retry_after_seconds = max(
        0,
        int(
            settings.document_summary_retry_after_seconds
            if retry_after_seconds is None
            else retry_after_seconds
        ),
    )

    with _SUMMARY_PROCESS_LOCK:
        return _run_document_summarization_internal(
            batch_size=safe_batch_size,
            include_failed=safe_include_failed,
            retry_after_seconds=safe_retry_after_seconds,
        )


def recover_interrupted_document_summaries() -> int:
    """Requeue documents left in running state by an interrupted worker process."""

    return chat_store.requeue_running_document_summaries(
        audit_reason="Summary worker startup recovery.",
    )


def request_document_summary_run() -> None:
    """Wake the worker so newly pending documents are processed quickly."""

    _WORKER_WAKE_EVENT.set()


def start_document_summary_job(
    *,
    job_id: str,
    include_failed: bool,
    retry_after_seconds: int,
    batch_size: int,
) -> None:
    """Process a full admin-triggered summary job with persisted progress updates."""

    existing_job = chat_store.get_summary_job(job_id)
    if existing_job is None:
        raise LookupError("Summary job not found.")

    safe_include_failed = bool(include_failed)
    safe_retry_after_seconds = max(0, int(retry_after_seconds))
    safe_batch_size = max(1, int(batch_size))

    with _SUMMARY_PROCESS_LOCK:
        chat_store.update_summary_job(
            job_id,
            status=chat_store.SUMMARY_JOB_STATUS_RUNNING,
            started_at=_utc_now_iso(),
            include_failed=safe_include_failed,
            retry_after_seconds=safe_retry_after_seconds,
            batch_size=safe_batch_size,
            processed_documents=0,
            completed_documents=0,
            failed_documents=0,
            current_document_id=None,
            error_message=None,
            completed_at=None,
        )

        processed_documents = 0
        completed_documents = 0
        failed_documents = 0

        try:
            total_documents = chat_store.count_documents_for_summary(
                include_failed=safe_include_failed,
                retry_after_seconds=safe_retry_after_seconds,
            )
            chat_store.update_summary_job(
                job_id,
                total_documents=total_documents,
            )

            while processed_documents < total_documents:
                stats = _run_document_summarization_internal(
                    batch_size=min(safe_batch_size, max(1, total_documents - processed_documents)),
                    include_failed=safe_include_failed,
                    retry_after_seconds=safe_retry_after_seconds,
                )
                if stats.claimed_documents <= 0:
                    break

                processed_documents += stats.claimed_documents
                completed_documents += stats.completed_documents
                failed_documents += stats.failed_documents

                chat_store.update_summary_job(
                    job_id,
                    processed_documents=processed_documents,
                    completed_documents=completed_documents,
                    failed_documents=failed_documents,
                )

            chat_store.update_summary_job(
                job_id,
                status=chat_store.SUMMARY_JOB_STATUS_COMPLETED,
                processed_documents=processed_documents,
                completed_documents=completed_documents,
                failed_documents=failed_documents,
                current_document_id=None,
                completed_at=_utc_now_iso(),
                error_message=None,
            )
            if processed_documents > 0:
                refresh_rag_caches()
        except Exception as exc:  # pragma: no cover - integration-heavy path
            logger.exception("Summary job failed", extra={"job_id": job_id})
            chat_store.update_summary_job(
                job_id,
                status=chat_store.SUMMARY_JOB_STATUS_FAILED,
                processed_documents=processed_documents,
                completed_documents=completed_documents,
                failed_documents=failed_documents,
                current_document_id=None,
                completed_at=_utc_now_iso(),
                error_message=_normalize_exception_message(exc),
            )


def _worker_loop(
    *,
    poll_interval_seconds: int,
    batch_size: int,
    include_failed: bool,
    retry_after_seconds: int,
) -> None:
    logger.info(
        "Document summary worker started",
        extra={
            "poll_interval_seconds": poll_interval_seconds,
            "batch_size": batch_size,
            "include_failed": include_failed,
            "retry_after_seconds": retry_after_seconds,
        },
    )

    while not _WORKER_STOP_EVENT.is_set():
        try:
            stats = run_document_summarization_once(
                batch_size=batch_size,
                include_failed=include_failed,
                retry_after_seconds=retry_after_seconds,
            )
            if stats.claimed_documents > 0:
                logger.info(
                    "Document summary worker batch completed",
                    extra={
                        "claimed_documents": stats.claimed_documents,
                        "completed_documents": stats.completed_documents,
                        "failed_documents": stats.failed_documents,
                    },
                )
        except Exception:  # pragma: no cover - defensive loop guard
            logger.exception("Unhandled exception in document summary worker loop")

        _WORKER_WAKE_EVENT.wait(timeout=poll_interval_seconds)
        _WORKER_WAKE_EVENT.clear()

    logger.info("Document summary worker stopped")


def start_document_summary_worker() -> bool:
    """Start a single in-process summary worker thread when enabled."""

    settings = get_settings()
    if not settings.document_summary_worker_enabled:
        logger.info("Document summary worker is disabled by configuration")
        return False

    with _WORKER_GUARD:
        global _WORKER_THREAD

        if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
            return False

        requeued = recover_interrupted_document_summaries()
        if requeued > 0:
            logger.info("Requeued interrupted summary documents", extra={"count": requeued})

        _WORKER_STOP_EVENT.clear()
        _WORKER_WAKE_EVENT.clear()

        _WORKER_THREAD = threading.Thread(
            target=_worker_loop,
            kwargs={
                "poll_interval_seconds": settings.document_summary_poll_interval_seconds,
                "batch_size": settings.document_summary_batch_size,
                "include_failed": settings.document_summary_retry_failed_enabled,
                "retry_after_seconds": settings.document_summary_retry_after_seconds,
            },
            name="document-summary-worker",
            daemon=True,
        )
        _WORKER_THREAD.start()
        return True


def stop_document_summary_worker(*, join_timeout_seconds: float = 5.0) -> bool:
    """Stop the worker thread if it is running."""

    with _WORKER_GUARD:
        global _WORKER_THREAD

        if _WORKER_THREAD is None:
            return True

        _WORKER_STOP_EVENT.set()
        _WORKER_WAKE_EVENT.set()
        _WORKER_THREAD.join(timeout=join_timeout_seconds)

        stopped = not _WORKER_THREAD.is_alive()
        if stopped:
            _WORKER_THREAD = None
        return stopped
