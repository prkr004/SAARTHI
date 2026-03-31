"""
Core RAG query logic — embedding retrieval, LLM invocation, and source formatting.
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.llms.ollama import OllamaLLM
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate

from temporal.comparator import compare_clauses
from temporal.version_retriever import (
    get_latest_two_versions,
    infer_document_title_from_query,
)

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
INDEX_PATH = "faiss_index"
DEFAULT_K = 4
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"

# ── Known-document registry ─────────────────────────────────────────────
# Maps filename substrings (lower-cased) to a friendly name and an
# official URL where the public can read the original circular.
_KNOWN_DOCUMENTS: list[dict] = [
    # ── Digital Lending ─────────────────────────────────────────────────
    {
        "pattern": "digitallending",
        "name": "RBI Guidelines on Digital Lending",
        "url": "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12382",
    },
    {
        "pattern": "digital_lending_2022",
        "name": "RBI Digital Lending Guidelines (2022)",
        "url": "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12382",
    },
    {
        "pattern": "digital_lending_2025",
        "name": "RBI Digital Lending Guidelines (2025)",
        "url": "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12382",
    },
    {
        "pattern": "dlg",
        "name": "Digital Lending Guidelines — Detailed Reference",
        "url": "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12382",
    },
    # ── KYC ─────────────────────────────────────────────────────────────
    {
        "pattern": "masterdirectionkyc",
        "name": "RBI Master Direction on KYC",
        "url": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566",
    },
    {
        "pattern": "kyc",
        "name": "RBI Master Direction on KYC",
        "url": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566",
    },
    # ── Digital Personal Data Protection Act ────────────────────────────
    {
        "pattern": "dpdp",
        "name": "Digital Personal Data Protection Act, 2023",
        "url": "https://www.meity.gov.in/writereaddata/files/Digital%20Personal%20Data%20Protection%20Act%202023.pdf",
    },
]


def _match_known_document(raw_source: str) -> Tuple[str, Optional[str]]:
    """Return (friendly_name, url) for a source path, or a cleaned-up
    filename and ``None`` if no known mapping exists."""
    lowered = raw_source.lower()
    for entry in _KNOWN_DOCUMENTS:
        if entry["pattern"] in lowered:
            return entry["name"], entry["url"]
    # Fallback — just show the filename without full path or extension
    stem = Path(raw_source).stem
    # Remove long hex suffixes common in auto-generated filenames
    stem = re.sub(r"[A-F0-9]{20,}$", "", stem, flags=re.IGNORECASE).rstrip("_- ")
    return stem or Path(raw_source).name, None


def format_source_label(metadata: dict) -> Tuple[str, Optional[str], Optional[int]]:
    """Public helper used by the UI to build citation labels.

    Returns
    -------
    (document_name, official_url_or_None, page_or_None)
    """
    raw_source = metadata.get("source", "Unknown source")
    page = metadata.get("page")
    doc_name, url = _match_known_document(raw_source)
    return doc_name, url, page


# ── Prompt template ─────────────────────────────────────────────────────
PROMPT_TEMPLATE = """You are SAARTHI — a Smart AI Assistant for Regulatory Tracking, Harmonisation & Insights,
specialising in RBI (Reserve Bank of India) guidelines.
Use ONLY the context below to answer the question. Be precise and reference specific
sections or clause numbers when available.

Context:
{context}

Question:
{question}

If the answer is not in the context, reply:
"The requested information was not found in the indexed documents. Please try rephrasing your question or ensure the relevant circular has been ingested."
"""

prompt = PromptTemplate(
    template=PROMPT_TEMPLATE,
    input_variables=["context", "question"],
)


# ── Cached loaders ──────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_embeddings():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def load_vectorstore(index_path: str = INDEX_PATH) -> FAISS:
    if not Path(index_path).exists():
        raise FileNotFoundError(
            f"FAISS index not found at '{index_path}'. "
            "Run `python build_vectorstore.py` to create it."
        )
    return FAISS.load_local(
        index_path,
        get_embeddings(),
        allow_dangerous_deserialization=True,
    )


@lru_cache(maxsize=4)
def get_llm(model_name: str = DEFAULT_OLLAMA_MODEL) -> OllamaLLM:
    return OllamaLLM(model=model_name)


# ── Standard RAG ────────────────────────────────────────────────────────
def ask_question(
    question: str,
    k: int = DEFAULT_K,
    model_name: str = DEFAULT_OLLAMA_MODEL,
) -> dict:
    """Retrieve relevant chunks and generate an answer.

    Returns ``{"answer": str, "sources": list[dict]}``
    """
    if not question or not question.strip():
        raise ValueError("Please enter a question before submitting.")

    vectorstore = load_vectorstore()
    retriever = vectorstore.as_retriever(search_kwargs={"k": k})
    docs = retriever.invoke(question)

    if not docs:
        return {
            "answer": (
                "No relevant sections were found for your query. "
                "Try rephrasing or broadening your question."
            ),
            "sources": [],
        }

    context = "\n\n".join(doc.page_content for doc in docs)
    final_prompt = prompt.format(context=context, question=question)
    answer = get_llm(model_name=model_name).invoke(final_prompt)

    sources = [
        {"content": doc.page_content, "metadata": doc.metadata}
        for doc in docs
    ]
    return {"answer": answer, "sources": sources}


# ── Temporal / version-comparison query ─────────────────────────────────
def ask_temporal_question(
    question: str,
    k: int = DEFAULT_K,
    model_name: str = DEFAULT_OLLAMA_MODEL,
    comparison_method: str = "both",
) -> dict:
    """Handle a temporal / version-comparison query.

    Workflow
    -------
    1. Infer which ``document_title`` the user asks about via similarity
       search.
    2. Retrieve the two most recent versions of that document.
    3. Run clause-level comparison (difflib and/or LLM).

    Returns a dict with comparison results or fallback RAG answer.
    """
    vectorstore = load_vectorstore()

    # Step 1 — figure out which document the user means
    document_title = infer_document_title_from_query(vectorstore, question, k=k)

    if document_title is None:
        logger.info("No document_title metadata found — falling back to normal RAG.")
        result = ask_question(question, k=k, model_name=model_name)
        result["fallback"] = True
        result["fallback_reason"] = "no_metadata"
        return result

    # Step 2 — get the two latest versions
    current_chunks, previous_chunks, current_date, previous_date = (
        get_latest_two_versions(vectorstore, document_title)
    )

    if current_chunks is None:
        logger.info("No chunks found for title='%s' — falling back.", document_title)
        result = ask_question(question, k=k, model_name=model_name)
        result["fallback"] = True
        result["fallback_reason"] = "no_chunks"
        return result

    if previous_chunks is None:
        return {
            "fallback": False,
            "single_version": True,
            "document_title": document_title,
            "current_date": current_date,
        }

    # Step 3 — clause-level comparison
    embeddings = get_embeddings()
    llm = get_llm(model_name=model_name) if comparison_method in ("llm", "both") else None

    comparison = compare_clauses(
        query=question,
        old_chunks=previous_chunks,
        new_chunks=current_chunks,
        embeddings=embeddings,
        llm=llm,
        method=comparison_method,
    )

    return {
        "fallback": False,
        "single_version": False,
        "comparison": comparison,
        "current_date": current_date,
        "previous_date": previous_date,
        "document_title": document_title,
    }


# ── CLI entry-point (for quick testing) ─────────────────────────────────
if __name__ == "__main__":
    print("\n=== SAARTHI — Regulatory RAG CLI ===\n")
    while True:
        query = input("Ask SAARTHI (or 'exit' to quit): ").strip()
        if query.lower() == "exit":
            break
        try:
            result = ask_question(query)
            print("\n📌  ANSWER:\n")
            print(result["answer"])
            if result["sources"]:
                print("\n📄  Sources:")
                for i, s in enumerate(result["sources"], 1):
                    name, url, pg = format_source_label(s["metadata"])
                    pg_str = f" (p. {pg})" if pg is not None else ""
                    print(f"  {i}. {name}{pg_str}")
        except Exception as exc:
            print(f"\n⚠  Error: {exc}\n")
