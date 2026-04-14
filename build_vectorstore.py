"""
Build (or rebuild) the FAISS vector store from PDFs in the data/ directory.

Usage
-----
    python build_vectorstore.py
    python build_vectorstore.py --manifest data/corpus_manifest.json

This script uses the metadata-aware ingestion pipeline so that every
chunk carries regulatory metadata (regulator, document_title,
version_date, etc.) needed for temporal change tracking.

To add a new document version without rebuilding from scratch, use
``ingestion.vectorstore_builder.add_to_vectorstore()`` instead.
"""

from __future__ import annotations

import argparse
import logging

from ingestion.vectorstore_builder import build_vectorstore_from_manifest

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_MANIFEST_PATH = "data/corpus_manifest.json"
INDEX_PATH = "faiss_index"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the FAISS index from a corpus manifest.")
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST_PATH,
        help=f"Path to corpus manifest JSON (default: {DEFAULT_MANIFEST_PATH})",
    )
    parser.add_argument(
        "--index-path",
        default=INDEX_PATH,
        help=f"Directory to save FAISS index (default: {INDEX_PATH})",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    logger.info("Starting vector-store build from manifest: %s", args.manifest)

    build_vectorstore_from_manifest(
        manifest_path=args.manifest,
        index_path=args.index_path,
    )

    logger.info("Vector store saved to '%s'. Ready to query.", args.index_path)


if __name__ == "__main__":
    main()
