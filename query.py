"""
Core RAG query logic — embedding retrieval, LLM invocation, and source formatting.
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional, Tuple

from langchain_community.embeddings import HuggingFaceEmbeddings
# Prefer the standalone provider package when available (newer LangChain split).
try:
    from langchain_ollama import OllamaLLM
except ImportError:  # pragma: no cover - fallback for older langchain-community installs
    from langchain_community.llms import Ollama as OllamaLLM
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
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
DEFAULT_HYBRID_VECTOR_WEIGHT = 0.7
DEFAULT_HYBRID_KEYWORD_WEIGHT = 0.3
DEFAULT_HYBRID_CANDIDATE_MULTIPLIER = 4
DEFAULT_HYBRID_KEYWORD_MIN_TOKEN_LENGTH = 3

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

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


@lru_cache(maxsize=1)
def get_hybrid_retrieval_settings() -> dict[str, float | int]:
    """Load hybrid retrieval controls from backend settings if available.

    Falls back to environment/default values when running standalone.
    """
    vector_weight = DEFAULT_HYBRID_VECTOR_WEIGHT
    keyword_weight = DEFAULT_HYBRID_KEYWORD_WEIGHT
    candidate_multiplier = DEFAULT_HYBRID_CANDIDATE_MULTIPLIER
    keyword_min_token_length = DEFAULT_HYBRID_KEYWORD_MIN_TOKEN_LENGTH

    try:
        from backend.app.core.config import get_settings

        settings = get_settings()
        vector_weight = float(settings.hybrid_vector_weight)
        keyword_weight = float(settings.hybrid_keyword_weight)
        candidate_multiplier = int(settings.hybrid_candidate_multiplier)
        keyword_min_token_length = int(settings.hybrid_keyword_min_token_length)
    except Exception:
        vector_weight = float(os.getenv("SAARTHI_HYBRID_VECTOR_WEIGHT", vector_weight))
        keyword_weight = float(os.getenv("SAARTHI_HYBRID_KEYWORD_WEIGHT", keyword_weight))
        candidate_multiplier = int(
            os.getenv("SAARTHI_HYBRID_CANDIDATE_MULTIPLIER", candidate_multiplier)
        )
        keyword_min_token_length = int(
            os.getenv(
                "SAARTHI_HYBRID_KEYWORD_MIN_TOKEN_LENGTH",
                keyword_min_token_length,
            )
        )

    vector_weight = max(vector_weight, 0.0)
    keyword_weight = max(keyword_weight, 0.0)
    total_weight = vector_weight + keyword_weight
    if total_weight <= 0:
        vector_weight = DEFAULT_HYBRID_VECTOR_WEIGHT
        keyword_weight = DEFAULT_HYBRID_KEYWORD_WEIGHT
        total_weight = vector_weight + keyword_weight

    return {
        "vector_weight": vector_weight / total_weight,
        "keyword_weight": keyword_weight / total_weight,
        "candidate_multiplier": max(1, candidate_multiplier),
        "keyword_min_token_length": max(1, keyword_min_token_length),
    }


def _tokenize(text: str, min_token_length: int) -> set[str]:
    if not text:
        return set()
    return {
        token.lower()
        for token in _TOKEN_RE.findall(text)
        if len(token) >= min_token_length
    }


def _doc_key(doc: Document) -> tuple[str, str, str]:
    metadata = getattr(doc, "metadata", {}) or {}
    source = str(metadata.get("source", ""))
    page = str(metadata.get("page", ""))
    snippet = (getattr(doc, "page_content", "") or "")[:200]
    return source, page, snippet


def _iter_all_docs(vectorstore: FAISS) -> Iterable[Document]:
    docstore = getattr(vectorstore, "docstore", None)
    mapping = getattr(vectorstore, "index_to_docstore_id", {})
    if docstore is None:
        return []

    docs: list[Document] = []
    for doc_id in mapping.values():
        doc = docstore.search(doc_id)
        if doc is not None:
            docs.append(doc)
    return docs


def _keyword_score(doc: Document, query_tokens: set[str], min_token_length: int) -> float:
    if not query_tokens:
        return 0.0

    metadata = getattr(doc, "metadata", {}) or {}
    searchable = " ".join(
        [
            getattr(doc, "page_content", "") or "",
            str(metadata.get("document_title", "")),
            str(metadata.get("source", "")),
            str(metadata.get("regulator", "")),
        ]
    )
    doc_tokens = _tokenize(searchable, min_token_length)
    if not doc_tokens:
        return 0.0

    overlap = query_tokens.intersection(doc_tokens)
    if not overlap:
        return 0.0

    coverage = len(overlap) / len(query_tokens)
    title_tokens = _tokenize(str(metadata.get("document_title", "")), min_token_length)
    title_overlap = (
        len(query_tokens.intersection(title_tokens)) / len(query_tokens)
        if title_tokens
        else 0.0
    )
    return coverage + (0.35 * title_overlap)


def _vector_candidates(
    vectorstore: FAISS,
    question: str,
    pool_k: int,
) -> tuple[list[Document], dict[tuple[str, str, str], float]]:
    try:
        scored = vectorstore.similarity_search_with_score(question, k=pool_k)
    except Exception:
        scored = []

    if scored:
        docs = [doc for doc, _ in scored if doc is not None]
        distances = [float(distance) for _, distance in scored]
        min_distance = min(distances)
        max_distance = max(distances)

        normalized: dict[tuple[str, str, str], float] = {}
        for doc, distance in scored:
            if doc is None:
                continue
            if max_distance == min_distance:
                score = 1.0
            else:
                score = 1.0 - ((float(distance) - min_distance) / (max_distance - min_distance))
            normalized[_doc_key(doc)] = max(0.0, min(1.0, score))
        return docs, normalized

    docs = vectorstore.similarity_search(question, k=pool_k)
    normalized = {}
    count = len(docs)
    for idx, doc in enumerate(docs):
        if count <= 1:
            normalized[_doc_key(doc)] = 1.0
        else:
            normalized[_doc_key(doc)] = 1.0 - (idx / (count - 1))
    return docs, normalized


def _keyword_candidates(
    vectorstore: FAISS,
    question: str,
    pool_k: int,
    min_token_length: int,
) -> tuple[list[Document], dict[tuple[str, str, str], float]]:
    query_tokens = _tokenize(question, min_token_length)
    if not query_tokens:
        return [], {}

    scored: list[tuple[Document, float]] = []
    for doc in _iter_all_docs(vectorstore):
        score = _keyword_score(doc, query_tokens, min_token_length)
        if score > 0:
            scored.append((doc, score))

    if not scored:
        return [], {}

    scored.sort(key=lambda item: item[1], reverse=True)
    top = scored[:pool_k]
    max_score = top[0][1]
    normalized = {
        _doc_key(doc): (score / max_score if max_score > 0 else 0.0)
        for doc, score in top
    }
    docs = [doc for doc, _ in top]
    return docs, normalized


def retrieve_relevant_docs(
    vectorstore: FAISS,
    question: str,
    k: int,
) -> list[Document]:
    """Retrieve top-k chunks using weighted vector + keyword hybrid ranking."""
    settings = get_hybrid_retrieval_settings()
    pool_k = max(k, int(settings["candidate_multiplier"]) * k)

    vector_docs, vector_scores = _vector_candidates(vectorstore, question, pool_k)
    keyword_docs, keyword_scores = _keyword_candidates(
        vectorstore,
        question,
        pool_k,
        int(settings["keyword_min_token_length"]),
    )

    if not vector_docs and not keyword_docs:
        return []

    merged_docs: dict[tuple[str, str, str], Document] = {}
    for doc in vector_docs:
        merged_docs[_doc_key(doc)] = doc
    for doc in keyword_docs:
        merged_docs[_doc_key(doc)] = doc

    weighted: list[tuple[float, float, float, Document]] = []
    vector_weight = float(settings["vector_weight"])
    keyword_weight = float(settings["keyword_weight"])

    for key, doc in merged_docs.items():
        vector_score = vector_scores.get(key, 0.0)
        keyword_score = keyword_scores.get(key, 0.0)
        combined = (vector_weight * vector_score) + (keyword_weight * keyword_score)
        weighted.append((combined, vector_score, keyword_score, doc))

    weighted.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    selected_docs = [doc for _, _, _, doc in weighted[:k]]

    if not selected_docs:
        return vector_docs[:k]

    logger.debug(
        "Hybrid retrieval selected %d docs (vector_candidates=%d, keyword_candidates=%d)",
        len(selected_docs),
        len(vector_docs),
        len(keyword_docs),
    )
    return selected_docs


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
    docs = retrieve_relevant_docs(vectorstore, question, k)

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
