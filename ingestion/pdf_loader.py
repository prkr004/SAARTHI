"""
Enhanced PDF loader that attaches regulatory metadata to every chunk.

Usage
-----
    from ingestion.pdf_loader import load_and_chunk_pdf

    docs = load_and_chunk_pdf(
        pdf_path="data/my_regulation.pdf",
        regulator="RBI",
        document_title="Guidelines on Digital Lending",
        version_date="2022-09-02",
        effective_date="2022-11-30",
        status="Active",
    )

The returned list of LangChain ``Document`` objects will have the temporal
metadata baked into ``doc.metadata`` alongside the standard ``source`` and
``page`` keys.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ingestion.metadata_schema import ChunkMetadata

logger = logging.getLogger(__name__)

# Defaults that match the existing build_vectorstore.py behaviour
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200


def load_and_chunk_pdf(
    pdf_path: str,
    regulator: Optional[str] = None,
    document_title: Optional[str] = None,
    version_date: Optional[str] = None,
    effective_date: Optional[str] = None,
    status: Optional[str] = "Active",
    amends: Optional[str] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list:
    """Load a PDF and return chunked Documents with full regulatory metadata.

    Parameters
    ----------
    pdf_path : str
        Path to the PDF file.
    regulator, document_title, version_date, effective_date, status, amends
        Regulatory metadata (all optional for backward compatibility).
    chunk_size, chunk_overlap
        Chunking parameters forwarded to ``RecursiveCharacterTextSplitter``.

    Returns
    -------
    list[Document]
        LangChain ``Document`` objects ready for embedding.
    """
    pdf_path = str(Path(pdf_path).resolve())
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    loader = PyPDFLoader(pdf_path)
    raw_docs = loader.load()
    logger.info("Loaded %d raw pages from %s", len(raw_docs), pdf_path)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = splitter.split_documents(raw_docs)
    logger.info("Split into %d chunks", len(chunks))

    # Enrich every chunk with temporal metadata
    for chunk in chunks:
        meta = ChunkMetadata.from_dict(chunk.metadata)
        meta.regulator = regulator
        meta.document_title = document_title
        meta.version_date = version_date
        meta.effective_date = effective_date
        meta.status = status
        meta.amends = amends
        chunk.metadata = meta.to_dict()

    return chunks
