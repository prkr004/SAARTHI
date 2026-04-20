"""Registry-driven FAISS reindex orchestration for safe update/delete propagation."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Iterable
from uuid import uuid4

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

import chat_store
from ingestion.vectorstore_builder import EMBEDDING_MODEL

from backend.app.core.config import get_settings
from backend.app.services.rag_cache_service import refresh_rag_caches

logger = logging.getLogger(__name__)

INDEX_WRITE_LOCK = Lock()
_REINDEX_PAGE_SIZE = 500


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split()).strip()
    return cleaned or None


def _normalize_key(value: object) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    return text.lower()


def _resolve_index_directory() -> Path:
    settings = get_settings()
    configured = Path(settings.faiss_index_path)
    if configured.suffix.lower() == ".faiss":
        return configured.parent.resolve()
    return configured.resolve()


def _chunk_tuple_key(metadata: dict) -> tuple[str, str, str]:
    source = _normalize_key(metadata.get("source"))
    title = _normalize_key(metadata.get("document_title"))
    version = _normalize_key(metadata.get("version_date")) or _normalize_key(metadata.get("effective_date"))
    return source, title, version


def _chunk_document_key(metadata: dict) -> str:
    source, title, version = _chunk_tuple_key(metadata)
    return f"{source}|{title}|{version}"


def _list_registry_rows_for_reindex() -> list[dict]:
    rows: list[dict] = []
    offset = 0

    while True:
        page = chat_store.list_documents_for_admin(
            include_deleted=True,
            limit=_REINDEX_PAGE_SIZE,
            offset=offset,
        )
        if not page:
            break

        rows.extend(page)
        if len(page) < _REINDEX_PAGE_SIZE:
            break

        offset += len(page)

    return rows


def _build_registry_lookup(rows: Iterable[dict]) -> dict[str, dict]:
    active_by_document_key: dict[str, dict] = {}
    deleted_by_document_key: dict[str, dict] = {}
    active_by_tuple: dict[tuple[str, str, str], dict] = {}
    deleted_by_tuple: dict[tuple[str, str, str], dict] = {}

    for row in rows:
        is_deleted = int(row.get("is_deleted") or 0) == 1
        document_key = _normalize_key(row.get("document_key"))
        row_tuple = (
            _normalize_key(row.get("source")),
            _normalize_key(row.get("document_title")),
            _normalize_key(row.get("version_date")) or _normalize_key(row.get("effective_date")),
        )

        if is_deleted:
            if document_key and document_key not in deleted_by_document_key:
                deleted_by_document_key[document_key] = row
            if row_tuple[0] and row_tuple[1] and row_tuple not in deleted_by_tuple:
                deleted_by_tuple[row_tuple] = row
            continue

        if document_key and document_key not in active_by_document_key:
            active_by_document_key[document_key] = row
        if row_tuple[0] and row_tuple[1] and row_tuple not in active_by_tuple:
            active_by_tuple[row_tuple] = row

    return {
        "active_by_document_key": active_by_document_key,
        "deleted_by_document_key": deleted_by_document_key,
        "active_by_tuple": active_by_tuple,
        "deleted_by_tuple": deleted_by_tuple,
    }


def _lookup_registry_row(metadata: dict, registry_lookup: dict[str, dict]) -> tuple[dict | None, bool]:
    chunk_key = _chunk_document_key(metadata)
    if chunk_key:
        deleted_match = registry_lookup["deleted_by_document_key"].get(chunk_key)
        if deleted_match is not None:
            return deleted_match, True

        active_match = registry_lookup["active_by_document_key"].get(chunk_key)
        if active_match is not None:
            return active_match, False

    chunk_tuple = _chunk_tuple_key(metadata)
    if chunk_tuple[0] and chunk_tuple[1]:
        deleted_match = registry_lookup["deleted_by_tuple"].get(chunk_tuple)
        if deleted_match is not None:
            return deleted_match, True

        active_match = registry_lookup["active_by_tuple"].get(chunk_tuple)
        if active_match is not None:
            return active_match, False

    return None, False


def _apply_registry_metadata(doc: Document, row: dict) -> Document:
    metadata = dict(getattr(doc, "metadata", {}) or {})

    metadata["source"] = row.get("source")
    metadata["document_title"] = row.get("document_title")
    metadata["version_date"] = row.get("version_date")
    metadata["effective_date"] = row.get("effective_date")
    metadata["regulator"] = row.get("regulator")
    metadata["status"] = row.get("document_status")
    metadata["document_status"] = row.get("document_status")
    metadata["document_key"] = row.get("document_key")

    return Document(page_content=getattr(doc, "page_content", ""), metadata=metadata)


def _project_registry_aware_docs(existing_docs: Iterable[Document], registry_lookup: dict[str, dict]) -> tuple[list[Document], dict[str, int]]:
    projected: list[Document] = []
    matched_chunks = 0
    dropped_chunks = 0
    metadata_updates = 0

    for doc in existing_docs:
        metadata = dict(getattr(doc, "metadata", {}) or {})
        row, is_deleted = _lookup_registry_row(metadata, registry_lookup)

        if row is None:
            projected.append(doc)
            continue

        matched_chunks += 1

        if is_deleted:
            dropped_chunks += 1
            continue

        updated_doc = _apply_registry_metadata(doc, row)
        if dict(getattr(updated_doc, "metadata", {}) or {}) != metadata:
            metadata_updates += 1

        projected.append(updated_doc)

    stats = {
        "matched_chunks": matched_chunks,
        "dropped_chunks": dropped_chunks,
        "metadata_updates": metadata_updates,
    }
    return projected, stats


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


def _remove_path(path: Path) -> None:
    if not path.exists():
        return

    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _save_empty_index(index_directory: Path, embeddings: HuggingFaceEmbeddings) -> None:
    try:
        import faiss
        from langchain_community.docstore.in_memory import InMemoryDocstore
    except Exception as exc:  # pragma: no cover - environment specific import behavior
        raise RuntimeError("Unable to create an empty index for reindexing.") from exc

    probe = embeddings.embed_query("dimension probe")
    dimension = len(probe)
    if dimension <= 0:
        raise ValueError("Embedding dimension must be greater than zero.")

    index = faiss.IndexFlatL2(dimension)
    vectorstore = FAISS(
        embedding_function=embeddings,
        index=index,
        docstore=InMemoryDocstore({}),
        index_to_docstore_id={},
    )
    vectorstore.save_local(str(index_directory))


def _build_temp_index_directory(index_directory: Path, docs: list[Document]) -> Path:
    temp_directory = index_directory.parent / f"{index_directory.name}__rebuild_{uuid4().hex}"
    _remove_path(temp_directory)

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    if docs:
        vectorstore = FAISS.from_documents(docs, embeddings)
        vectorstore.save_local(str(temp_directory))
    else:
        _save_empty_index(temp_directory, embeddings)

    return temp_directory


def _atomic_swap_index_directories(index_directory: Path, rebuilt_directory: Path) -> None:
    previous_directory = index_directory.parent / f"{index_directory.name}__previous"
    _remove_path(previous_directory)

    moved_current = False
    if index_directory.exists():
        index_directory.rename(previous_directory)
        moved_current = True

    try:
        rebuilt_directory.rename(index_directory)
    except Exception:
        if moved_current and previous_directory.exists() and not index_directory.exists():
            previous_directory.rename(index_directory)
        raise


def run_registry_reindex(
    *,
    trigger: str,
    document_id: int | None = None,
    actor_user_id: int | None = None,
) -> dict:
    """Rebuild the retrieval index from current chunks with registry-consistent metadata/deletes."""

    safe_trigger = _normalize_text(trigger) or "unknown"
    outcome = {
        "success": False,
        "trigger": safe_trigger,
        "document_id": document_id,
        "actor_user_id": actor_user_id,
        "reason": "not_started",
        "registry_documents": 0,
        "total_chunks_before": 0,
        "total_chunks_after": 0,
        "matched_chunks": 0,
        "dropped_chunks": 0,
        "metadata_updates": 0,
    }

    temp_directory: Path | None = None

    with INDEX_WRITE_LOCK:
        index_directory = _resolve_index_directory()
        outcome["index_directory"] = str(index_directory)

        if not index_directory.exists():
            outcome["reason"] = "index_missing"
            logger.warning(
                "Registry reindex skipped because index directory is missing.",
                extra={
                    "trigger": safe_trigger,
                    "document_id": document_id,
                    "actor_user_id": actor_user_id,
                    "index_directory": str(index_directory),
                },
            )
            return outcome

        try:
            existing_docs = _load_index_documents(index_directory)
            outcome["total_chunks_before"] = len(existing_docs)

            rows = _list_registry_rows_for_reindex()
            outcome["registry_documents"] = len(rows)
            registry_lookup = _build_registry_lookup(rows)

            projected_docs, stats = _project_registry_aware_docs(existing_docs, registry_lookup)
            outcome.update(stats)
            outcome["total_chunks_after"] = len(projected_docs)

            if stats["dropped_chunks"] == 0 and stats["metadata_updates"] == 0:
                outcome["success"] = True
                outcome["reason"] = "no_registry_delta"
                return outcome

            temp_directory = _build_temp_index_directory(index_directory, projected_docs)
            _atomic_swap_index_directories(index_directory, temp_directory)
            temp_directory = None

            refresh_rag_caches()

            outcome["success"] = True
            outcome["reason"] = "reindexed"
            logger.info(
                "Registry reindex completed.",
                extra={
                    "trigger": safe_trigger,
                    "document_id": document_id,
                    "actor_user_id": actor_user_id,
                    "index_directory": str(index_directory),
                    "total_chunks_before": outcome["total_chunks_before"],
                    "total_chunks_after": outcome["total_chunks_after"],
                    "dropped_chunks": outcome["dropped_chunks"],
                    "metadata_updates": outcome["metadata_updates"],
                },
            )
        except Exception as exc:  # pragma: no cover - integration-heavy path
            logger.exception(
                "Registry reindex failed.",
                extra={
                    "trigger": safe_trigger,
                    "document_id": document_id,
                    "actor_user_id": actor_user_id,
                    "index_directory": str(index_directory),
                },
            )
            outcome["reason"] = "reindex_failed"
            outcome["error_message"] = str(exc)
        finally:
            if temp_directory is not None and temp_directory.exists():
                _remove_path(temp_directory)

    return outcome
