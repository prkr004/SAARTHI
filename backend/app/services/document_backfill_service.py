"""Backfill service that projects indexed chunks into the document registry."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Sequence

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

import chat_store
from ingestion.metadata_schema import validate_manifest_entry
from ingestion.vectorstore_builder import EMBEDDING_MODEL

from backend.app.core.config import get_settings
from backend.app.services.document_summary_service import request_document_summary_run
from backend.app.services.rag_cache_service import refresh_rag_caches

logger = logging.getLogger(__name__)

DEFAULT_MANIFEST_PATH = Path("data") / "corpus_manifest.json"

_BACKFILL_LOCK = Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split()).strip()
    return cleaned or None


def _normalize_source_key(value: object) -> str:
    cleaned = _normalize_text(value)
    if not cleaned:
        return ""
    normalized = cleaned.replace("\\", "/")
    return normalized.rsplit("/", 1)[-1].lower()


def _normalize_source_value(source: object, *, fallback_title: str | None, fallback_version: str | None) -> str:
    cleaned = _normalize_text(source)
    if cleaned:
        return cleaned

    title_part = (fallback_title or "unknown_document").strip().lower().replace(" ", "_")
    version_part = (fallback_version or "unknown").strip().lower().replace(" ", "_")
    return f"unknown_source|{title_part}|{version_part}"


def _infer_title_from_source(source: str) -> str | None:
    source_key = _normalize_source_key(source)
    if not source_key:
        return None
    stem = Path(source_key).stem
    pretty = stem.replace("_", " ").replace("-", " ").strip()
    return pretty.title() if pretty else None


def _resolve_index_directory() -> Path:
    settings = get_settings()
    configured = Path(settings.faiss_index_path)
    if configured.suffix.lower() == ".faiss":
        return configured.parent.resolve()
    return configured.resolve()


def _load_manifest_entries(manifest_path: Path | None = None) -> list[dict]:
    target_path = manifest_path or DEFAULT_MANIFEST_PATH
    resolved = target_path.resolve()
    if not resolved.exists():
        return []

    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive parsing fallback
        logger.warning("Unable to parse backfill manifest at %s: %s", resolved, exc)
        return []

    if not isinstance(payload, list):
        logger.warning("Backfill manifest is not a JSON list: %s", resolved)
        return []

    entries: list[dict] = []
    for idx, raw in enumerate(payload, start=1):
        try:
            normalized = validate_manifest_entry(raw, entry_index=idx)
        except ValueError as exc:
            logger.warning("Skipping invalid manifest entry #%d during backfill: %s", idx, exc)
            continue
        entries.append(normalized)
    return entries


def _build_manifest_lookup(entries: Sequence[dict]) -> tuple[dict[str, list[dict]], dict[tuple[str, str], list[dict]]]:
    by_source: dict[str, list[dict]] = defaultdict(list)
    by_title_version: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for entry in entries:
        source_key = _normalize_source_key(entry.get("pdf_path"))
        if source_key:
            by_source[source_key].append(entry)

        title = (_normalize_text(entry.get("document_title")) or "").lower()
        version = (_normalize_text(entry.get("version_date")) or "").lower()
        if title and version:
            by_title_version[(title, version)].append(entry)

    return by_source, by_title_version


def _find_manifest_match(
    *,
    source: str | None,
    document_title: str | None,
    version_date: str | None,
    by_source: dict[str, list[dict]],
    by_title_version: dict[tuple[str, str], list[dict]],
) -> dict | None:
    normalized_title = (_normalize_text(document_title) or "").lower()
    normalized_version = (_normalize_text(version_date) or "").lower()

    source_key = _normalize_source_key(source)
    if source_key and source_key in by_source:
        candidates = by_source[source_key]
        if normalized_title and normalized_version:
            for entry in candidates:
                entry_title = (_normalize_text(entry.get("document_title")) or "").lower()
                entry_version = (_normalize_text(entry.get("version_date")) or "").lower()
                if entry_title == normalized_title and entry_version == normalized_version:
                    return entry
        return candidates[0]

    if normalized_title and normalized_version:
        candidates = by_title_version.get((normalized_title, normalized_version), [])
        if candidates:
            return candidates[0]

    return None


def _extract_chunk_field(metadata: dict, *keys: str) -> str | None:
    for key in keys:
        if key in metadata:
            value = _normalize_text(metadata.get(key))
            if value:
                return value
    return None


def _manifest_entry_group(entry: dict) -> tuple[tuple[str, str, str], dict]:
    source = _normalize_source_value(
        entry.get("pdf_path"),
        fallback_title=_normalize_text(entry.get("document_title")),
        fallback_version=_normalize_text(entry.get("version_date")) or _normalize_text(entry.get("effective_date")),
    )
    document_title = _normalize_text(entry.get("document_title")) or _infer_title_from_source(source) or "Unknown Document"
    version_date = _normalize_text(entry.get("version_date")) or _normalize_text(entry.get("effective_date"))
    effective_date = _normalize_text(entry.get("effective_date"))
    regulator = _normalize_text(entry.get("regulator"))
    document_status = _normalize_text(entry.get("status"))

    key_source = source.lower()
    key_title = document_title.lower()
    key_version = (version_date or "").lower()
    group_key = (key_source, key_title, key_version)
    document_key = f"{key_source}|{key_title}|{key_version}"

    return (
        group_key,
        {
            "document_key": document_key,
            "source": source,
            "document_title": document_title,
            "version_date": version_date,
            "effective_date": effective_date,
            "regulator": regulator,
            "document_status": document_status,
            "chunk_count": 0,
            "metadata": {
                "backfill_origin": "manifest_only",
                "manifest_enriched": True,
                "source_candidates": {source},
                "pages": [],
            },
        },
    )


def group_indexed_documents(chunks: Sequence[Document], manifest_entries: Sequence[dict] | None = None) -> list[dict]:
    entries = list(manifest_entries or [])
    by_source, by_title_version = _build_manifest_lookup(entries)

    grouped: dict[tuple[str, str, str], dict] = {}

    for chunk in chunks:
        metadata = dict(getattr(chunk, "metadata", {}) or {})

        source = _extract_chunk_field(metadata, "source", "pdf_path", "file_path")
        document_title = _extract_chunk_field(metadata, "document_title", "title")
        version_date = _extract_chunk_field(metadata, "version_date")
        effective_date = _extract_chunk_field(metadata, "effective_date")
        regulator = _extract_chunk_field(metadata, "regulator")
        document_status = _extract_chunk_field(metadata, "status", "document_status")

        manifest_match = _find_manifest_match(
            source=source,
            document_title=document_title,
            version_date=version_date or effective_date,
            by_source=by_source,
            by_title_version=by_title_version,
        )

        source = source or _normalize_text(manifest_match.get("pdf_path")) if manifest_match else source
        document_title = document_title or _normalize_text(manifest_match.get("document_title")) if manifest_match else document_title
        version_date = version_date or _normalize_text(manifest_match.get("version_date")) if manifest_match else version_date
        effective_date = effective_date or _normalize_text(manifest_match.get("effective_date")) if manifest_match else effective_date
        regulator = regulator or _normalize_text(manifest_match.get("regulator")) if manifest_match else regulator
        document_status = document_status or _normalize_text(manifest_match.get("status")) if manifest_match else document_status

        source = _normalize_source_value(
            source,
            fallback_title=document_title,
            fallback_version=version_date or effective_date,
        )
        document_title = _normalize_text(document_title) or _infer_title_from_source(source) or "Unknown Document"
        version_date = _normalize_text(version_date) or _normalize_text(effective_date)
        effective_date = _normalize_text(effective_date)
        regulator = _normalize_text(regulator)
        document_status = _normalize_text(document_status)

        key_source = source.lower()
        key_title = document_title.lower()
        key_version = (version_date or "").lower()
        group_key = (key_source, key_title, key_version)

        document_key = f"{key_source}|{key_title}|{key_version}"

        if group_key not in grouped:
            grouped[group_key] = {
                "document_key": document_key,
                "source": source,
                "document_title": document_title,
                "version_date": version_date,
                "effective_date": effective_date,
                "regulator": regulator,
                "document_status": document_status,
                "chunk_count": 0,
                "metadata": {
                    "backfill_origin": "indexed_chunks",
                    "manifest_enriched": bool(manifest_match),
                    "source_candidates": set(),
                    "pages": [],
                },
            }

        group = grouped[group_key]
        group["chunk_count"] += 1
        group["metadata"]["manifest_enriched"] = bool(group["metadata"]["manifest_enriched"] or manifest_match)

        source_candidate = _extract_chunk_field(metadata, "source", "pdf_path", "file_path")
        if source_candidate:
            group["metadata"]["source_candidates"].add(source_candidate)

        page_value = metadata.get("page")
        if isinstance(page_value, int):
            group["metadata"]["pages"].append(page_value)

    alias_to_group_key: dict[tuple[str, str, str], tuple[str, str, str]] = {}
    for existing_group_key, group in grouped.items():
        alias_key = (
            _normalize_source_key(group.get("source")),
            (_normalize_text(group.get("document_title")) or "").lower(),
            (_normalize_text(group.get("version_date")) or "").lower(),
        )
        if alias_key[0]:
            alias_to_group_key[alias_key] = existing_group_key

    # Include manifest rows that were not represented by indexed chunks so sync can
    # recover complete registry visibility from canonical corpus definitions.
    for entry in entries:
        group_key, manifest_group = _manifest_entry_group(entry)

        alias_key = (
            _normalize_source_key(manifest_group.get("source")),
            (_normalize_text(manifest_group.get("document_title")) or "").lower(),
            (_normalize_text(manifest_group.get("version_date")) or "").lower(),
        )

        resolved_group_key = alias_to_group_key.get(alias_key, group_key)

        if resolved_group_key in grouped:
            group = grouped[resolved_group_key]
            group["metadata"]["manifest_enriched"] = True
            group["metadata"]["source_candidates"].add(manifest_group["source"])

            if not _normalize_text(group.get("effective_date")) and _normalize_text(manifest_group.get("effective_date")):
                group["effective_date"] = manifest_group["effective_date"]
            if not _normalize_text(group.get("regulator")) and _normalize_text(manifest_group.get("regulator")):
                group["regulator"] = manifest_group["regulator"]
            if not _normalize_text(group.get("document_status")) and _normalize_text(manifest_group.get("document_status")):
                group["document_status"] = manifest_group["document_status"]

            continue

        grouped[group_key] = manifest_group
        if alias_key[0]:
            alias_to_group_key[alias_key] = group_key

    grouped_docs = list(grouped.values())
    for doc in grouped_docs:
        pages: list[int] = sorted(doc["metadata"].pop("pages"))
        if pages:
            doc["metadata"]["page_min"] = pages[0]
            doc["metadata"]["page_max"] = pages[-1]
        doc["metadata"]["source_candidates"] = sorted(doc["metadata"]["source_candidates"])

    grouped_docs.sort(key=lambda item: item["document_key"])
    return grouped_docs


def _load_index_documents(index_directory: Path) -> list[Document]:
    if not index_directory.exists():
        raise FileNotFoundError(f"Vector index directory not found: {index_directory}")

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vectorstore = FAISS.load_local(
        str(index_directory),
        embeddings,
        allow_dangerous_deserialization=True,
    )

    mapping: dict[int, str] = getattr(vectorstore, "index_to_docstore_id", {})
    docstore = getattr(vectorstore, "docstore", None)
    if docstore is None:
        return []

    docs: list[Document] = []
    for docstore_id in mapping.values():
        doc = docstore.search(docstore_id)
        if doc is not None:
            docs.append(doc)
    return docs


def start_document_backfill_job(*, job_id: str, manifest_path: str | None = None) -> None:
    """Populate document registry from existing indexed chunks."""

    existing_job = chat_store.get_backfill_job(job_id)
    if existing_job is None:
        raise LookupError("Backfill job not found.")

    created_by = int(existing_job["created_by"])

    with _BACKFILL_LOCK:
        chat_store.update_backfill_job(
            job_id,
            status=chat_store.BACKFILL_STATUS_RUNNING,
            started_at=_utc_now_iso(),
            total_documents=0,
            processed_documents=0,
            discovered_chunks=0,
            progress_percent=0,
            current_document_key=None,
            error_message=None,
            completed_at=None,
        )

        try:
            index_directory = _resolve_index_directory()
            chunks = _load_index_documents(index_directory)
            manifest_entries = _load_manifest_entries(Path(manifest_path) if manifest_path else None)
            grouped_docs = group_indexed_documents(chunks, manifest_entries=manifest_entries)

            total_documents = len(grouped_docs)
            discovered_chunks = sum(int(item["chunk_count"]) for item in grouped_docs)

            chat_store.update_backfill_job(
                job_id,
                total_documents=total_documents,
                discovered_chunks=discovered_chunks,
                processed_documents=0,
                progress_percent=0,
            )

            if total_documents == 0:
                chat_store.update_backfill_job(
                    job_id,
                    status=chat_store.BACKFILL_STATUS_COMPLETED,
                    progress_percent=100,
                    completed_at=_utc_now_iso(),
                )
                refresh_rag_caches()
                request_document_summary_run()
                return

            for index, grouped in enumerate(grouped_docs, start=1):
                chat_store.upsert_document_registry_entry(
                    document_key=str(grouped["document_key"]),
                    source=str(grouped["source"]),
                    document_title=str(grouped["document_title"]),
                    version_date=grouped.get("version_date"),
                    effective_date=grouped.get("effective_date"),
                    regulator=grouped.get("regulator"),
                    document_status=grouped.get("document_status"),
                    chunk_count=int(grouped["chunk_count"]),
                    metadata=dict(grouped.get("metadata") or {}),
                    actor_user_id=created_by,
                    audit_reason=f"Backfilled from existing indexed chunks (job={job_id})",
                )

                progress_percent = int((index / total_documents) * 100)
                chat_store.update_backfill_job(
                    job_id,
                    processed_documents=index,
                    progress_percent=progress_percent,
                    current_document_key=str(grouped["document_key"]),
                )

            chat_store.update_backfill_job(
                job_id,
                status=chat_store.BACKFILL_STATUS_COMPLETED,
                processed_documents=total_documents,
                progress_percent=100,
                current_document_key=None,
                completed_at=_utc_now_iso(),
            )
            refresh_rag_caches()
            request_document_summary_run()
        except Exception as exc:  # pragma: no cover - integration-heavy path
            logger.exception("Document backfill job failed", extra={"job_id": job_id})
            chat_store.update_backfill_job(
                job_id,
                status=chat_store.BACKFILL_STATUS_FAILED,
                progress_percent=100,
                current_document_key=None,
                error_message=str(exc),
                completed_at=_utc_now_iso(),
            )
