"""
Build (or rebuild) the FAISS vector store from PDFs in the data/ directory.

Usage
-----
    python build_vectorstore.py

This script uses the metadata-aware ingestion pipeline so that every
chunk carries regulatory metadata (regulator, document_title,
version_date, etc.) needed for temporal change tracking.

To add a new document version without rebuilding from scratch, use
``ingestion.vectorstore_builder.add_to_vectorstore()`` instead.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from ingestion.vectorstore_builder import build_vectorstore

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ── Document configurations ─────────────────────────────────────────────
# Each entry describes one PDF to ingest. Add new circulars here.
PDF_CONFIGS: list[dict] = [
    # ── Digital Lending Guidelines (2022) ───────────────────────────────
    {
        "pdf_path": r"data\digital_lending_2022.pdf.pdf",
        "regulator": "RBI",
        "document_title": "Guidelines on Digital Lending",
        "version_date": "2022-09-02",
        "effective_date": "2022-11-30",
        "status": "Superseded",
    },
    # ── Digital Lending Guidelines (2025) ───────────────────────────────
    {
        "pdf_path": r"data\digital_lending_2025.pdf.pdf",
        "regulator": "RBI",
        "document_title": "Guidelines on Digital Lending",
        "version_date": "2025-04-01",
        "effective_date": "2025-04-01",
        "status": "Active",
        "amends": "2022-09-02 version",
    },
    # ── Digital Lending Guidelines — Detailed Reference ─────────────────
    {
        "pdf_path": r"data\DLG.pdf",
        "regulator": "RBI",
        "document_title": "Digital Lending Guidelines — Detailed Reference",
        "version_date": "2022-09-02",
        "effective_date": "2022-11-30",
        "status": "Active",
    },
    # ── Original long-named DL circular (kept for coverage) ─────────────
    {
        "pdf_path": r"data\GUIDELINESDIGITALLENDINGD5C35A71D8124A0E92AEB940A7D25BB3.pdf",
        "regulator": "RBI",
        "document_title": "Guidelines on Digital Lending",
        "version_date": "2022-09-02",
        "effective_date": "2022-11-30",
        "status": "Superseded",
    },
    # ── Digital Personal Data Protection Act, 2023 ──────────────────────
    {
        "pdf_path": r"data\DPDP_2023.pdf",
        "regulator": "Government of India",
        "document_title": "Digital Personal Data Protection Act 2023",
        "version_date": "2023-08-11",
        "effective_date": "2023-08-11",
        "status": "Active",
    },
    # ── Master Direction — KYC ──────────────────────────────────────────
    {
        "pdf_path": r"data\MasterDirectionKYC.pdf",
        "regulator": "RBI",
        "document_title": "Master Direction on KYC",
        "version_date": "2016-02-25",
        "effective_date": "2016-02-25",
        "status": "Active",
    },
]

INDEX_PATH = "faiss_index"


def main() -> None:
    logger.info("Starting vector-store build …")

    # Validate all paths first
    for cfg in PDF_CONFIGS:
        p = Path(cfg["pdf_path"])
        if not p.exists():
            logger.error("PDF not found: %s", p.resolve())
            sys.exit(1)

    build_vectorstore(
        pdf_configs=[dict(c) for c in PDF_CONFIGS],  # defensive copy
        index_path=INDEX_PATH,
    )

    logger.info("Vector store saved to '%s'. Ready to query.", INDEX_PATH)


if __name__ == "__main__":
    main()
