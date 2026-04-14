"""
Metadata-aware vector-store builder.

Supports two workflows:

1. **Build from scratch** — index one or more PDFs with metadata.
2. **Manifest build** — load a JSON corpus manifest and index all entries.
3. **Incremental add** — load an existing FAISS index and append new
   document chunks without rebuilding the entire store.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from ingestion.metadata_schema import validate_manifest_entry
from ingestion.pdf_loader import load_and_chunk_pdf

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_INDEX_PATH = "faiss_index"
DEFAULT_MANIFEST_PATH = "data/corpus_manifest.json"


def _get_embeddings(model_name: str = EMBEDDING_MODEL) -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=model_name)


def build_vectorstore(
    pdf_configs: List[dict],
    index_path: str = DEFAULT_INDEX_PATH,
    embedding_model: str = EMBEDDING_MODEL,
    strict_metadata: bool = False,
) -> FAISS:
    """Build (or rebuild) a FAISS index from a list of PDF configurations.

    Parameters
    ----------
    pdf_configs : list[dict]
        Each dict must have a ``pdf_path`` key and may include any of the
        metadata keys accepted by ``load_and_chunk_pdf`` (regulator,
        document_title, version_date, effective_date, status, amends).
    index_path : str
        Where to save the FAISS index on disk.
    embedding_model : str
        HuggingFace model identifier for the embedding function.
    strict_metadata : bool
        When ``True``, enforce strict metadata validation during PDF loading.

    Returns
    -------
    FAISS
        The persisted vector store object.
    """
    embeddings = _get_embeddings(embedding_model)
    all_chunks = []

    for cfg in pdf_configs:
        config = dict(cfg)
        pdf_path = config.pop("pdf_path")
        chunks = load_and_chunk_pdf(
            pdf_path=pdf_path,
            strict_metadata=strict_metadata,
            **config,
        )
        all_chunks.extend(chunks)
        logger.info("Loaded %d chunks from %s", len(chunks), pdf_path)

    if not all_chunks:
        raise ValueError("No chunks produced — check your PDF paths.")

    vectorstore = FAISS.from_documents(all_chunks, embeddings)
    vectorstore.save_local(index_path)
    logger.info("Saved FAISS index with %d chunks to %s", len(all_chunks), index_path)
    return vectorstore


def load_pdf_configs_from_manifest(manifest_path: str = DEFAULT_MANIFEST_PATH) -> List[dict[str, Any]]:
    """Load and validate corpus entries from a JSON manifest.

    Manifest entries are validated strictly through
    ``ingestion.metadata_schema.validate_manifest_entry``.
    """
    manifest_file = Path(manifest_path).resolve()
    if not manifest_file.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_file}")

    try:
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Manifest at '{manifest_file}' is not valid JSON.") from exc

    if not isinstance(payload, list):
        raise ValueError("Corpus manifest must be a JSON array of entries.")

    if not payload:
        raise ValueError("Corpus manifest is empty. Add at least one entry.")

    configs: List[dict[str, Any]] = []
    for idx, raw_entry in enumerate(payload, start=1):
        entry = validate_manifest_entry(raw_entry, entry_index=idx)

        pdf_path = Path(entry["pdf_path"])
        if not pdf_path.is_absolute():
            pdf_path = (manifest_file.parent / pdf_path).resolve()
        else:
            pdf_path = pdf_path.resolve()

        if not pdf_path.exists():
            raise FileNotFoundError(
                f"Manifest entry #{idx} references missing PDF: {pdf_path}"
            )

        entry["pdf_path"] = str(pdf_path)
        configs.append(entry)

    return configs


def build_vectorstore_from_manifest(
    manifest_path: str = DEFAULT_MANIFEST_PATH,
    index_path: str = DEFAULT_INDEX_PATH,
    embedding_model: str = EMBEDDING_MODEL,
) -> FAISS:
    """Build a FAISS index from a strict metadata corpus manifest."""
    configs = load_pdf_configs_from_manifest(manifest_path=manifest_path)
    return build_vectorstore(
        pdf_configs=configs,
        index_path=index_path,
        embedding_model=embedding_model,
        strict_metadata=True,
    )


def add_to_vectorstore(
    pdf_path: str,
    index_path: str = DEFAULT_INDEX_PATH,
    embedding_model: str = EMBEDDING_MODEL,
    strict_metadata: bool = False,
    **metadata_kwargs,
) -> FAISS:
    """Add a new PDF (version) to an *existing* FAISS index.

    This is the preferred method for ingesting a newer version of a
    regulation so that both old and new chunks coexist in the store.

    Parameters
    ----------
    pdf_path : str
        Path to the new PDF.
    index_path : str
        Path to the existing FAISS index directory.
    embedding_model : str
        HuggingFace model identifier.
    strict_metadata : bool
        When ``True``, enforce strict metadata validation during PDF loading.
    **metadata_kwargs
        Forwarded to ``load_and_chunk_pdf`` (regulator, document_title, …).

    Returns
    -------
    FAISS
        The updated vector store.
    """
    embeddings = _get_embeddings(embedding_model)

    if Path(index_path).exists():
        vectorstore = FAISS.load_local(
            index_path, embeddings, allow_dangerous_deserialization=True
        )
        logger.info("Loaded existing index from %s", index_path)
    else:
        logger.warning("No existing index at %s — creating new one.", index_path)
        vectorstore = None

    chunks = load_and_chunk_pdf(
        pdf_path=pdf_path,
        strict_metadata=strict_metadata,
        **metadata_kwargs,
    )

    if vectorstore is None:
        vectorstore = FAISS.from_documents(chunks, embeddings)
    else:
        vectorstore.add_documents(chunks)

    vectorstore.save_local(index_path)
    logger.info("Added %d chunks; index saved to %s", len(chunks), index_path)
    return vectorstore
