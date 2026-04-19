"""Admin document ingestion orchestration with persistent job tracking."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Iterable

from fastapi import UploadFile
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

import chat_store
from ingestion.pdf_loader import load_and_chunk_pdf
from ingestion.vectorstore_builder import EMBEDDING_MODEL

from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "application/octet-stream",
}
_ALLOWED_SUFFIX = ".pdf"
_FILENAME_SANITIZER = re.compile(r"[^A-Za-z0-9._-]+")

_FAISS_WRITE_LOCK = Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_iso_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _sanitize_filename(name: str, fallback: str) -> str:
    cleaned = _FILENAME_SANITIZER.sub("_", name).strip("._-")
    return cleaned or fallback


def _resolve_index_directory() -> Path:
    settings = get_settings()
    configured = Path(settings.faiss_index_path)
    if configured.suffix.lower() == ".faiss":
        return configured.parent.resolve()
    return configured.resolve()


def _refresh_rag_cache() -> None:
    # The query module memoizes FAISS and embedding instances. Clear those so
    # newly ingested chunks become queryable immediately without restarts.
    try:
        import query

        query.load_vectorstore.cache_clear()
        query.get_embeddings.cache_clear()
    except Exception as exc:  # pragma: no cover - defensive cache refresh
        logger.warning("Unable to refresh query cache after ingestion: %s", exc)


def _infer_metadata_from_file(path: Path) -> dict:
    title = path.stem.replace("_", " ").replace("-", " ").strip()
    if not title:
        title = "Uploaded Regulatory Document"
    return {
        "regulator": "Admin Upload",
        "document_title": title,
        "version_date": _today_iso_date(),
        "effective_date": _today_iso_date(),
        "status": "Active",
        "amends": None,
    }


def _load_or_initialize_store(index_directory: Path, embeddings: HuggingFaceEmbeddings, first_chunks: list):
    if index_directory.exists():
        vectorstore = FAISS.load_local(
            str(index_directory),
            embeddings,
            allow_dangerous_deserialization=True,
        )
        # Always append the first file's chunks even when loading an existing index.
        vectorstore.add_documents(first_chunks)
        return vectorstore
    return FAISS.from_documents(first_chunks, embeddings)


async def persist_uploaded_pdfs(files: list[UploadFile]) -> list[Path]:
    """Validate uploads and persist PDFs to controlled admin upload storage."""

    settings = get_settings()

    if not files:
        raise ValueError("Select at least one PDF file.")

    if len(files) > settings.admin_upload_max_files_per_job:
        raise ValueError(
            f"Too many files. Maximum allowed per job is {settings.admin_upload_max_files_per_job}."
        )

    max_bytes = settings.admin_upload_max_file_size_mb * 1024 * 1024
    upload_root = Path(settings.admin_upload_directory).resolve()
    job_folder = upload_root / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    job_folder.mkdir(parents=True, exist_ok=False)

    persisted_files: list[Path] = []

    for index, upload in enumerate(files, start=1):
        incoming_name = upload.filename or f"document_{index}.pdf"
        safe_name = _sanitize_filename(incoming_name, fallback=f"document_{index}.pdf")
        extension = Path(safe_name).suffix.lower()
        if extension != _ALLOWED_SUFFIX:
            raise ValueError(f"Only PDF files are allowed. Invalid file: {incoming_name}")

        if upload.content_type and upload.content_type.lower() not in _ALLOWED_CONTENT_TYPES:
            raise ValueError(f"Unsupported content type for {incoming_name}: {upload.content_type}")

        payload = await upload.read()
        await upload.close()

        if not payload:
            raise ValueError(f"Uploaded file is empty: {incoming_name}")
        if len(payload) > max_bytes:
            raise ValueError(
                f"File exceeds size limit ({settings.admin_upload_max_file_size_mb}MB): {incoming_name}"
            )
        if not payload.startswith(b"%PDF"):
            raise ValueError(f"File is not a valid PDF stream: {incoming_name}")

        destination = job_folder / f"{index:02d}_{safe_name}"
        destination.write_bytes(payload)
        persisted_files.append(destination)

    return persisted_files


def start_ingestion_job(*, job_id: str, stored_files: Iterable[Path]) -> None:
    """Run ingestion for an existing job and continuously update job status."""

    files = list(stored_files)
    total_files = len(files)

    if total_files == 0:
        chat_store.update_ingestion_job(
            job_id,
            status=chat_store.INGESTION_STATUS_FAILED,
            error_message="No files available for ingestion.",
            completed_at=_utc_now_iso(),
            progress_percent=100,
        )
        return

    with _FAISS_WRITE_LOCK:
        chat_store.update_ingestion_job(
            job_id,
            status=chat_store.INGESTION_STATUS_RUNNING,
            started_at=_utc_now_iso(),
            processed_files=0,
            total_chunks=0,
            progress_percent=0,
            current_file=None,
            error_message=None,
        )

        try:
            index_directory = _resolve_index_directory()
            index_directory.parent.mkdir(parents=True, exist_ok=True)

            embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
            vectorstore = None
            processed_files = 0
            total_chunks = 0

            for path in files:
                if not path.exists():
                    raise FileNotFoundError(f"Uploaded file missing: {path}")

                chat_store.update_ingestion_job(
                    job_id,
                    current_file=path.name,
                )

                metadata = _infer_metadata_from_file(path)
                chunks = load_and_chunk_pdf(
                    pdf_path=str(path),
                    regulator=metadata["regulator"],
                    document_title=metadata["document_title"],
                    version_date=metadata["version_date"],
                    effective_date=metadata["effective_date"],
                    status=metadata["status"],
                    amends=metadata["amends"],
                    strict_metadata=False,
                )

                if not chunks:
                    raise RuntimeError(f"No chunks generated for {path.name}")

                if vectorstore is None:
                    vectorstore = _load_or_initialize_store(index_directory, embeddings, chunks)
                else:
                    vectorstore.add_documents(chunks)

                vectorstore.save_local(str(index_directory))

                processed_files += 1
                total_chunks += len(chunks)
                progress_percent = int((processed_files / total_files) * 100)

                chat_store.update_ingestion_job(
                    job_id,
                    processed_files=processed_files,
                    total_chunks=total_chunks,
                    progress_percent=progress_percent,
                    current_file=path.name,
                )

            _refresh_rag_cache()

            chat_store.update_ingestion_job(
                job_id,
                status=chat_store.INGESTION_STATUS_COMPLETED,
                processed_files=processed_files,
                total_chunks=total_chunks,
                progress_percent=100,
                current_file=None,
                error_message=None,
                completed_at=_utc_now_iso(),
            )
        except Exception as exc:  # pragma: no cover - integration-heavy path
            logger.exception("Ingestion job failed", extra={"job_id": job_id})
            chat_store.update_ingestion_job(
                job_id,
                status=chat_store.INGESTION_STATUS_FAILED,
                progress_percent=100,
                error_message=str(exc),
                completed_at=_utc_now_iso(),
            )
