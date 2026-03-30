"""
SAARTHI — Regulatory Q&A Assistant.

Streamlit front-end that wires together the retrieval pipeline (query.py),
temporal comparison logic, predefined responses, and a polished UI.
"""

from pathlib import Path

import streamlit as st

from query import (
    INDEX_PATH,
    ask_question,
    ask_temporal_question,
    format_source_label,
)

# ── Hardcoded optimal settings ──────────────────────────────────────
MODEL_NAME = "llama3"
TOP_K = 5                       # sweet-spot: enough context without noise
COMPARISON_METHOD = "both"      # textual diff + AI summary

from predefined_responses import get_predefined_response
from temporal.intent_detector import detect_temporal_intent
from ui.change_history import (
    render_change_history,
    render_no_metadata_notice,
    render_single_version_notice,
)

# ── Page config ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SAARTHI — Regulatory RAG Assistant",
    page_icon="📘",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Theme-aware CSS ─────────────────────────────────────────────────────
st.markdown(
    """
    <style>
      /* ── Layout ───────────────────────────────── */
      .block-container {
        padding-top: 2.5rem;
        padding-bottom: 4rem;
      }

      /* ── Welcome card ─────────────────────────── */
      .welcome-card {
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 12px;
        padding: 2rem 2rem 1.5rem;
        margin: 1.5rem 0 1rem;
        text-align: center;
      }
      .welcome-card h2 {
        margin: 0 0 0.35rem;
        font-size: 1.35rem;
        font-weight: 600;
      }
      .welcome-card p {
        opacity: 0.7;
        font-size: 0.92rem;
        margin: 0 0 1.1rem;
      }
      .welcome-pills {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 0.5rem;
      }
      .welcome-pills span {
        border: 1px solid rgba(128,128,128,0.3);
        border-radius: 20px;
        padding: 0.35rem 0.85rem;
        font-size: 0.8rem;
        opacity: 0.75;
      }

      /* ── Disclaimer (fixed below chat input) ── */
      .disclaimer-bottom {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        text-align: center;
        font-size: 0.73rem;
        padding: 0.45rem 1rem;
        z-index: 50;
        opacity: 0.75;
        border-top: 1px solid rgba(128,128,128,0.15);
        background: var(--background-color, #0e1117);
      }
      /* push Streamlit chat-input up to make room */
      [data-testid="stBottom"] {
        bottom: 1.8rem;
      }

      /* ── Footer ────────────────────────────────── */
      .app-footer {
        text-align: center;
        font-size: 0.72rem;
        opacity: 0.45;
        padding: 2.5rem 0 0.5rem;
      }

      /* ── Hide sidebar completely ────────────────── */
      [data-testid="collapsedControl"] { display: none; }
      section[data-testid="stSidebar"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ───────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []


# ── Reusable UI helpers ─────────────────────────────────────────────────
def _render_sources(sources: list) -> None:
    """Render retrieved source chunks with friendly document names and
    official links instead of raw file paths."""
    with st.expander("📄  View retrieved sources", expanded=False):
        for idx, src in enumerate(sources, start=1):
            doc_name, doc_link, page = format_source_label(src.get("metadata", {}))
            page_str = f", page {page}" if page is not None else ""

            if doc_link:
                title_md = f"[{doc_name}{page_str}]({doc_link})"
            else:
                title_md = f"{doc_name}{page_str}"

            st.markdown(f"**Source {idx}:** {title_md}")
            snippet = (src.get("content") or "")[:600]
            if snippet:
                st.caption(snippet)
            if idx < len(sources):
                st.divider()




# ── Header ──────────────────────────────────────────────────────────────
col_title, col_btn = st.columns([6, 1])
with col_title:
    st.markdown("## 📘 SAARTHI — Regulatory Q&A Assistant")
with col_btn:
    if st.button("🗑️", help="Clear chat history"):
        st.session_state.history = []
        st.rerun()
st.caption(
    "Ask questions grounded in indexed RBI regulatory documents. "
    "SAARTHI automatically detects when to compare versions across circular editions."
)

# ── Index check ─────────────────────────────────────────────────────────
if not Path(INDEX_PATH).exists():
    st.error(
        "**Vector index not found.**\n\n"
        "Please run the ingestion pipeline first:\n"
        "```\npython build_vectorstore.py\n```"
    )
    st.stop()

# ── Chat history replay ────────────────────────────────────────────────
for message in st.session_state.history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        sources = message.get("sources")
        if sources:
            _render_sources(sources)

# ── Welcome card (shown only when chat is empty) ────────────────────────
if not st.session_state.history:
    st.markdown(
        '<div class="welcome-card">'
        "<h2>Namaste! I'm SAARTHI 🙏</h2>"
        "<p>Your AI assistant for exploring RBI regulatory guidelines — "
        "digital lending, compliance requirements, KYC norms, and more.</p>"
        '<div class="welcome-pills">'
        "<span>What are the key digital lending guidelines?</span>"
        "<span>Explain the KYC requirements</span>"
        "<span>What is allowed for LSPs?</span>"
        "<span>Who are you?</span>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

# ── Chat input ──────────────────────────────────────────────────────────
question = st.chat_input("Ask SAARTHI a question about RBI regulatory guidelines…")

# ── Disclaimer (pinned below chat input) ────────────────────────────────
st.markdown(
    '<div class="disclaimer-bottom">'
    "⚠️ For informational purposes only — refer to the official "
    '<a href="https://www.rbi.org.in" target="_blank">RBI circulars</a> '
    "and consult qualified professionals before making compliance decisions."
    "</div>",
    unsafe_allow_html=True,
)

if question:
    st.session_state.history.append({"role": "user", "content": question})

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        # Check for predefined / canned responses first
        predefined = get_predefined_response(question)

        if predefined:
            answer = predefined
            sources = []
            st.markdown(answer)
            is_temporal = False

        elif (is_temporal := detect_temporal_intent(question)):
            # ── Temporal / version-comparison path (auto-detected) ──
            with st.spinner("SAARTHI is comparing document versions — this may take a moment…"):
                try:
                    result = ask_temporal_question(
                        question=question,
                        k=TOP_K,
                        model_name=MODEL_NAME,
                        comparison_method=COMPARISON_METHOD,
                    )
                except Exception as exc:
                    result = {
                        "fallback": True,
                        "fallback_reason": "exception",
                        "answer": (
                            "**Unable to complete version comparison.**\n\n"
                            "The system encountered an issue while comparing "
                            "document versions. Please verify that Ollama is "
                            "running and the selected model is available, then "
                            "try again.\n\n"
                            f"_Technical detail: {exc}_"
                        ),
                        "sources": [],
                    }

            if result.get("fallback"):
                answer = result.get("answer", "")
                sources = result.get("sources", [])
                st.markdown(answer)
                if sources:
                    _render_sources(sources)
                reason = result.get("fallback_reason", "")
                if reason == "no_metadata":
                    render_no_metadata_notice()
            elif result.get("single_version"):
                answer = (
                    "Only one version of this document is currently indexed. "
                    "Upload an earlier or newer version to enable change comparison."
                )
                sources = []
                st.markdown(answer)
                render_single_version_notice(
                    result.get("document_title"),
                    result.get("current_date"),
                )
            else:
                answer = result.get("comparison", {}).get(
                    "llm_summary",
                    result.get("comparison", {}).get("difflib_result", ""),
                )
                sources = []
                render_change_history(
                    result["comparison"],
                    result.get("current_date"),
                    result.get("previous_date"),
                )
        elif not predefined:
            # ── Standard RAG path ───────────────────────────────────
            with st.spinner("SAARTHI is retrieving relevant sections…"):
                try:
                    result = ask_question(
                        question=question,
                        k=TOP_K,
                        model_name=MODEL_NAME,
                    )
                    answer = result["answer"]
                    sources = result["sources"]
                except ConnectionError:
                    answer = (
                        "**Could not connect to the language model.**\n\n"
                        "Please ensure Ollama is running on your machine "
                        f"(`ollama serve`) and the model **{MODEL_NAME}** is available "
                        f"(`ollama pull {MODEL_NAME}`)."
                    )
                    sources = []
                except FileNotFoundError:
                    answer = (
                        "**Vector index not found.**\n\n"
                        "The FAISS index could not be loaded. Run "
                        "`python build_vectorstore.py` to create it."
                    )
                    sources = []
                except ValueError as ve:
                    answer = f"**Invalid input:** {ve}"
                    sources = []
                except Exception as exc:
                    answer = (
                        "**Something went wrong while processing your question.**\n\n"
                        "Please try rephrasing your query or check that Ollama "
                        "is running correctly.\n\n"
                        f"_Technical detail: {exc}_"
                    )
                    sources = []

            st.markdown(answer)
            if sources:
                _render_sources(sources)

    st.session_state.history.append(
        {
            "role": "assistant",
            "content": answer,
            "sources": sources if not is_temporal else [],
        }
    )

# ── Footer ──────────────────────────────────────────────────────────────
st.markdown(
    '<div class="app-footer">'
    "SAARTHI &middot; Regulatory Q&amp;A Assistant &middot; "
    "Powered by LangChain, FAISS &amp; Ollama &middot; "
    "For academic &amp; advisory use only"
    "</div>",
    unsafe_allow_html=True,
)
