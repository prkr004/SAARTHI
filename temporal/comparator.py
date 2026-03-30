"""
Clause-level comparison between two document versions.

Two strategies are provided and can be toggled via the ``method`` parameter:

1. **difflib** — pure-Python textual diff (fast, no LLM call).
2. **llm**     — sends both clause texts to the local Ollama model for a
   structured change explanation (richer, but slower).

Both are exposed through the single entry-point ``compare_clauses()``.
"""

from __future__ import annotations

import difflib
import logging
from typing import List, Optional

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1.  Find the most relevant clause in each version
# ---------------------------------------------------------------------------

def _best_clause(query: str, chunks: List[Document], embeddings) -> Optional[Document]:
    """Return the single chunk from *chunks* most similar to *query*.

    We build a tiny ephemeral FAISS index so we can reuse the same
    similarity-search logic without touching the main index.
    """
    if not chunks:
        return None
    try:
        mini_store = FAISS.from_documents(chunks, embeddings)
        results = mini_store.similarity_search(query, k=1)
        return results[0] if results else None
    except Exception as exc:
        logger.error("Clause retrieval failed: %s", exc)
        return chunks[0]  # safe fallback — return first chunk


# ---------------------------------------------------------------------------
# 2a.  difflib comparison
# ---------------------------------------------------------------------------

def _difflib_compare(old_text: str, new_text: str) -> str:
    """Return a human-readable unified diff between two texts."""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile="Previous Version",
        tofile="Current Version",
        lineterm="",
    )
    result = "\n".join(diff)
    return result if result.strip() else "(No textual differences detected.)"


# ---------------------------------------------------------------------------
# 2b.  LLM-based comparison
# ---------------------------------------------------------------------------

_LLM_COMPARISON_PROMPT = """You are a regulatory compliance analyst.

Compare the following two regulatory clauses and explain:
1. What was **added** in the new version.
2. What was **removed** from the old version.
3. What was **modified** (rephrased or adjusted).
4. The **practical compliance impact** of these changes.

Use ONLY the text provided below. Do NOT add external information.
If the clauses are identical, state that clearly.

--- PREVIOUS VERSION ---
{old_text}

--- CURRENT VERSION ---
{new_text}

Provide a structured summary.
"""


def _llm_compare(old_text: str, new_text: str, llm) -> str:
    """Ask the local Ollama model for a structured change summary."""
    prompt = _LLM_COMPARISON_PROMPT.format(old_text=old_text, new_text=new_text)
    try:
        return llm.invoke(prompt)
    except Exception as exc:
        logger.error("LLM comparison failed: %s", exc)
        return (
            "The AI-powered comparison is temporarily unavailable. "
            "Please ensure Ollama is running and try again.\n\n"
            f"_Technical detail: {exc}_"
        )


# ---------------------------------------------------------------------------
# 3.  Public entry-point
# ---------------------------------------------------------------------------

def compare_clauses(
    query: str,
    old_chunks: List[Document],
    new_chunks: List[Document],
    embeddings,
    llm=None,
    method: str = "both",
) -> dict:
    """Compare the most relevant clause across two document versions.

    Parameters
    ----------
    query : str
        The user's question (used for similarity matching).
    old_chunks, new_chunks : list[Document]
        Chunks belonging to the previous and current version respectively.
    embeddings
        Embedding model instance (HuggingFaceEmbeddings).
    llm : optional
        Ollama LLM instance.  Required only when *method* includes ``"llm"``.
    method : str
        ``"difflib"``, ``"llm"``, or ``"both"`` (default).

    Returns
    -------
    dict with keys:
        old_clause, new_clause       — raw texts
        difflib_result               — unified diff (if requested)
        llm_summary                  — LLM explanation (if requested)
        error                        — set only on failure
    """
    result: dict = {}

    old_doc = _best_clause(query, old_chunks, embeddings)
    new_doc = _best_clause(query, new_chunks, embeddings)

    if old_doc is None and new_doc is None:
        return {
            "error": (
                "No relevant clauses could be identified in either document "
                "version for your query. Try rephrasing your question or "
                "ensure the correct documents have been ingested."
            )
        }

    old_text = old_doc.page_content if old_doc else "(This clause was not present in the previous version.)"
    new_text = new_doc.page_content if new_doc else "(This clause was not present in the current version.)"

    result["old_clause"] = old_text
    result["new_clause"] = new_text

    if method in ("difflib", "both"):
        result["difflib_result"] = _difflib_compare(old_text, new_text)

    if method in ("llm", "both"):
        if llm is None:
            result["llm_summary"] = (
                "AI summary was not generated because the LLM was not "
                "configured for this comparison method."
            )
        else:
            result["llm_summary"] = _llm_compare(old_text, new_text, llm)

    return result
