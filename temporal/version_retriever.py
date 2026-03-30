"""
Version retrieval logic.

Given a ``document_title``, this module locates all indexed chunks that
belong to that document across versions, groups them by ``version_date``,
and returns the two most recent versions (current + previous) for
comparison.

Because FAISS does not support native metadata filtering, the fallback
strategy is to iterate over the full docstore and filter in Python.
This is acceptable for academic / mid-scale workloads (< 100 k chunks).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper: safe date parsing
# ---------------------------------------------------------------------------

_DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Try several formats; return ``None`` on failure instead of crashing."""
    if not date_str:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except (ValueError, TypeError):
            continue
    logger.warning("Could not parse date: %s", date_str)
    return None


# ---------------------------------------------------------------------------
# Core retrieval
# ---------------------------------------------------------------------------


def get_all_chunks_for_title(
    vectorstore: FAISS,
    document_title: str,
) -> List[Document]:
    """Return every chunk whose ``document_title`` metadata matches.

    Falls back to a full docstore scan because FAISS has no native
    metadata-filter API.
    """
    results: List[Document] = []
    docstore = vectorstore.docstore

    # FAISS wraps documents in an InMemoryDocstore keyed by string ids.
    for doc_id in vectorstore.index_to_docstore_id.values():
        doc = docstore.search(doc_id)
        if doc is None:
            continue
        meta = getattr(doc, "metadata", {})
        title = meta.get("document_title")
        if title and title.strip().lower() == document_title.strip().lower():
            results.append(doc)

    logger.info(
        "Found %d chunks for document_title='%s'", len(results), document_title
    )
    return results


def group_chunks_by_version(
    chunks: List[Document],
) -> Dict[str, List[Document]]:
    """Group a flat list of chunks into ``{version_date: [chunks]}``."""
    groups: Dict[str, List[Document]] = {}
    for chunk in chunks:
        vdate = chunk.metadata.get("version_date", "unknown")
        groups.setdefault(vdate, []).append(chunk)
    return groups


def get_latest_two_versions(
    vectorstore: FAISS,
    document_title: str,
) -> Tuple[Optional[List[Document]], Optional[List[Document]], Optional[str], Optional[str]]:
    """Retrieve chunks for the two most recent versions of a document.

    Returns
    -------
    (current_chunks, previous_chunks, current_date, previous_date)
        Any element may be ``None`` if fewer than two versions exist.
    """
    all_chunks = get_all_chunks_for_title(vectorstore, document_title)

    if not all_chunks:
        logger.warning("No chunks found for document_title='%s'", document_title)
        return None, None, None, None

    groups = group_chunks_by_version(all_chunks)

    # Sort version dates descending (newest first)
    sorted_dates = sorted(
        groups.keys(),
        key=lambda d: _parse_date(d) or datetime.min,
        reverse=True,
    )

    current_date = sorted_dates[0] if len(sorted_dates) >= 1 else None
    previous_date = sorted_dates[1] if len(sorted_dates) >= 2 else None

    current_chunks = groups.get(current_date) if current_date else None
    previous_chunks = groups.get(previous_date) if previous_date else None

    return current_chunks, previous_chunks, current_date, previous_date


def infer_document_title_from_query(
    vectorstore: FAISS,
    query: str,
    k: int = 4,
) -> Optional[str]:
    """Use a similarity search to guess which ``document_title`` the user is
    asking about.  Returns the most frequently occurring title among the
    top-k results, or ``None`` if no title metadata is present."""
    docs = vectorstore.similarity_search(query, k=k)
    title_counts: Dict[str, int] = {}
    for doc in docs:
        title = doc.metadata.get("document_title")
        if title:
            title_counts[title] = title_counts.get(title, 0) + 1

    if not title_counts:
        return None

    # Return the title with the highest count
    return max(title_counts, key=title_counts.get)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Index inspection helpers  (used by sidebar selectors)
# ---------------------------------------------------------------------------

def get_all_document_titles(index_path: str = "faiss_index") -> List[str]:
    """Return a sorted list of all unique ``document_title`` values in the index."""
    from pathlib import Path
    from langchain_community.embeddings import HuggingFaceEmbeddings

    if not Path(index_path).exists():
        return []
    try:
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        db = FAISS.load_local(
            index_path, embeddings, allow_dangerous_deserialization=True
        )
        titles: set[str] = set()
        for doc_id in db.index_to_docstore_id.values():
            doc = db.docstore.search(doc_id)
            if doc is None:
                continue
            title = getattr(doc, "metadata", {}).get("document_title")
            if title:
                titles.add(title)
        return sorted(titles)
    except Exception:
        return []


def get_all_versions_for_title(
    title: str, index_path: str = "faiss_index"
) -> List[str]:
    """Return sorted version_date values for a given document_title."""
    from pathlib import Path
    from langchain_community.embeddings import HuggingFaceEmbeddings

    if not Path(index_path).exists():
        return []
    try:
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        db = FAISS.load_local(
            index_path, embeddings, allow_dangerous_deserialization=True
        )
        dates: set[str] = set()
        for doc_id in db.index_to_docstore_id.values():
            doc = db.docstore.search(doc_id)
            if doc is None:
                continue
            meta = getattr(doc, "metadata", {})
            if meta.get("document_title") == title:
                vd = meta.get("version_date")
                if vd:
                    dates.add(vd)
        return sorted(dates, key=lambda d: _parse_date(d) or datetime.min)
    except Exception:
        return []
