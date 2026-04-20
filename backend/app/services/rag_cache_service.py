"""Helpers for refreshing cached RAG dependencies without process restarts."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def refresh_rag_caches() -> None:
    """Clear memoized query caches so retrieval reflects latest persisted state."""

    try:
        import query

        for cache_candidate in (
            getattr(query, "load_vectorstore", None),
            getattr(query, "get_embeddings", None),
            getattr(query, "get_llm", None),
            getattr(query, "get_hybrid_retrieval_settings", None),
        ):
            cache_clear = getattr(cache_candidate, "cache_clear", None)
            if callable(cache_clear):
                cache_clear()
    except Exception as exc:  # pragma: no cover - defensive cache refresh
        logger.warning("Unable to refresh query caches: %s", exc)
