"""
Metadata-aware vector-store builder.

Supports two workflows:

1. **Build from scratch** — index one or more PDFs with metadata.
2. **Incremental add** — load an existing FAISS index and append new
   document chunks without rebuilding the entire store.

The original ``build_vectorstore.py`` script stays untouched;
this module is a *parallel* entrypoint for metadata-rich ingestion.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from ingestion.pdf_loader import load_and_chunk_pdf

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_INDEX_PATH = "faiss_index"


def _get_embeddings(model_name: str = EMBEDDING_MODEL) -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=model_name)


def build_vectorstore(
    pdf_configs: List[dict],
    index_path: str = DEFAULT_INDEX_PATH,
    embedding_model: str = EMBEDDING_MODEL,
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

    Returns
    -------
    FAISS
        The persisted vector store object.
    """
    embeddings = _get_embeddings(embedding_model)
    all_chunks = []

    for cfg in pdf_configs:
        pdf_path = cfg.pop("pdf_path")
        chunks = load_and_chunk_pdf(pdf_path=pdf_path, **cfg)
        all_chunks.extend(chunks)
        logger.info("Loaded %d chunks from %s", len(chunks), pdf_path)

    if not all_chunks:
        raise ValueError("No chunks produced — check your PDF paths.")

    vectorstore = FAISS.from_documents(all_chunks, embeddings)
    vectorstore.save_local(index_path)
    logger.info("Saved FAISS index with %d chunks to %s", len(all_chunks), index_path)
    return vectorstore


def add_to_vectorstore(
    pdf_path: str,
    index_path: str = DEFAULT_INDEX_PATH,
    embedding_model: str = EMBEDDING_MODEL,
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

    chunks = load_and_chunk_pdf(pdf_path=pdf_path, **metadata_kwargs)

    if vectorstore is None:
        vectorstore = FAISS.from_documents(chunks, embeddings)
    else:
        vectorstore.add_documents(chunks)

    vectorstore.save_local(index_path)
    logger.info("Added %d chunks; index saved to %s", len(chunks), index_path)
    return vectorstore
