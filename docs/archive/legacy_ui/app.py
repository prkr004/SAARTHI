"""
SAARTHI — Regulatory Q&A Assistant.

Streamlit front-end that wires together the retrieval pipeline (query.py),
temporal comparison logic, predefined responses, and secure auth-backed chat storage.
"""

from pathlib import Path
import time

import streamlit as st

from chat_store import (
    add_message,
    authenticate_user,
    bootstrap_admin_user,
    create_conversation,
    delete_conversation,
    ensure_user_has_conversation,
    get_messages,
    initialize_db,
    list_conversations,
    rename_conversation,
    register_user,
)
from query import (
    INDEX_PATH,
    ask_question,
    ask_temporal_question,
    format_source_label,
)

# -- Import model configuration -------------------------------------------------
from models_config import AVAILABLE_MODELS, get_model_by_id, get_model_info_text, get_recommended_model

# -- Hardcoded optimal settings -------------------------------------------------
DEFAULT_MODEL = "phi:2.7b"
TOP_K = 5
COMPARISON_METHOD = "both"
SESSION_TIMEOUT_SECONDS = 30 * 60

from predefined_responses import get_predefined_response
from temporal.intent_detector import detect_temporal_intent
from ui.change_history import (
    render_change_history,
    render_no_metadata_notice,
    render_single_version_notice,
)

# -- Page config ----------------------------------------------------------------
st.set_page_config(
    page_title="SAARTHI - Regulatory RAG Assistant",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -- Theme-aware CSS ------------------------------------------------------------
st.markdown(
    """
    <style>
      .block-container {
        padding-top: 1.8rem;
        padding-bottom: 4rem;
      }

      .auth-shell {
        max-width: 860px;
        margin: 0 auto;
      }

      .auth-hero {
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 16px;
        padding: 1.3rem 1.4rem;
        margin-bottom: 1rem;
        background: linear-gradient(135deg, rgba(18, 42, 66, 0.10), rgba(175, 87, 51, 0.08));
      }

      .auth-hero h2 {
        margin: 0 0 0.35rem;
        font-size: 1.3rem;
      }

      .auth-note {
        opacity: 0.8;
        font-size: 0.88rem;
      }

      .welcome-card {
        border: 1px solid rgba(128,128,128,0.25);
        border-radius: 12px;
        padding: 2rem 2rem 1.5rem;
        margin: 1.2rem 0 1rem;
        text-align: center;
      }

      .welcome-card h2 {
        margin: 0 0 0.35rem;
        font-size: 1.3rem;
        font-weight: 600;
      }

      .welcome-card p {
        opacity: 0.72;
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

      [data-testid="stBottom"] {
        bottom: 1.8rem;
      }

      .app-footer {
        text-align: center;
        font-size: 0.72rem;
        opacity: 0.45;
        padding: 2.5rem 0 0.5rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_session_state() -> None:
    if "history" not in st.session_state:
        st.session_state.history = []

    if "selected_model" not in st.session_state:
        st.session_state.selected_model = get_recommended_model()

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None

    if "current_conversation_id" not in st.session_state:
        st.session_state.current_conversation_id = None

    if "last_activity_ts" not in st.session_state:
        st.session_state.last_activity_ts = time.time()

    if "rename_target_conversation_id" not in st.session_state:
        st.session_state.rename_target_conversation_id = None

    if "rename_draft_title" not in st.session_state:
        st.session_state.rename_draft_title = ""

    if "pending_delete_conversation_id" not in st.session_state:
        st.session_state.pending_delete_conversation_id = None


def _reset_auth_state() -> None:
    st.session_state.authenticated = False
    st.session_state.auth_user = None
    st.session_state.current_conversation_id = None
    st.session_state.history = []


def _enforce_session_timeout() -> None:
    if not st.session_state.authenticated:
        return

    now = time.time()
    elapsed = now - st.session_state.last_activity_ts
    if elapsed > SESSION_TIMEOUT_SECONDS:
        _reset_auth_state()
        st.warning("Session expired due to inactivity. Please login again.")
        st.rerun()

    st.session_state.last_activity_ts = now


def _load_conversation(conversation_id: int) -> None:
    user_id = int(st.session_state.auth_user["user_id"])
    st.session_state.history = get_messages(conversation_id=conversation_id, user_id=user_id)
    st.session_state.current_conversation_id = conversation_id


def _ensure_active_conversation() -> None:
    user_id = int(st.session_state.auth_user["user_id"])
    if st.session_state.current_conversation_id is None:
        st.session_state.current_conversation_id = ensure_user_has_conversation(user_id)
    try:
        _load_conversation(st.session_state.current_conversation_id)
    except PermissionError:
        st.session_state.current_conversation_id = ensure_user_has_conversation(user_id)
        _load_conversation(st.session_state.current_conversation_id)


def _switch_to_latest_or_new(user_id: int) -> None:
    conversations = list_conversations(user_id)
    if conversations:
        _load_conversation(int(conversations[0]["id"]))
    else:
        new_id = create_conversation(user_id=user_id, title="New Chat")
        _load_conversation(new_id)


def _render_sources(sources: list) -> None:
    with st.expander("📄 View retrieved sources", expanded=False):
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


def _render_auth_screen() -> None:
    st.markdown('<div class="auth-shell">', unsafe_allow_html=True)
    st.markdown(
        '<div class="auth-hero">'
        '<h2>Secure Employee Access - SAARTHI</h2>'
        '<div class="auth-note">Only authorized bank employees can use this workspace. '
        'Use your assigned Employee ID and strong password.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form", clear_on_submit=False):
            employee_id = st.text_input("Employee ID", max_chars=24, placeholder="EMP1234")
            password = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Login", use_container_width=True)

        if submit_login:
            auth_result = authenticate_user(employee_id=employee_id, password=password)
            if auth_result.success:
                st.session_state.authenticated = True
                st.session_state.auth_user = {
                    "user_id": int(auth_result.user_id),
                    "employee_id": auth_result.employee_id,
                    "full_name": auth_result.full_name,
                }
                st.session_state.current_conversation_id = ensure_user_has_conversation(auth_result.user_id)
                _load_conversation(st.session_state.current_conversation_id)
                st.success("Login successful.")
                st.rerun()
            else:
                st.error(auth_result.message)

    with tab_register:
        with st.form("register_form", clear_on_submit=True):
            full_name = st.text_input("Full Name", placeholder="Aman Sharma")
            employee_id = st.text_input("Employee ID", max_chars=24, placeholder="EMP1234")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            submit_register = st.form_submit_button("Create Account", use_container_width=True)

        st.caption(
            "Password policy: minimum 12 chars, include upper + lower + number + special character."
        )

        if submit_register:
            if password != confirm_password:
                st.error("Passwords do not match.")
            else:
                result = register_user(
                    employee_id=employee_id,
                    full_name=full_name,
                    password=password,
                )
                if result.success:
                    st.success(result.message)
                else:
                    st.error(result.message)

    st.markdown("</div>", unsafe_allow_html=True)


def _render_sidebar() -> None:
    user = st.session_state.auth_user
    user_id = int(user["user_id"])

    st.sidebar.markdown("### Employee Workspace")
    st.sidebar.caption(f"User: {user['full_name']} ({user['employee_id']})")

    if st.sidebar.button("+ New Chat", use_container_width=True):
        new_id = create_conversation(user_id=user_id, title="New Chat")
        st.session_state.current_conversation_id = new_id
        st.session_state.history = []
        st.session_state.rename_target_conversation_id = None
        st.session_state.pending_delete_conversation_id = None
        st.rerun()

    st.sidebar.markdown("#### Your Chats")
    conversations = list_conversations(user_id=user_id)

    pending_delete_id = st.session_state.pending_delete_conversation_id
    if pending_delete_id is not None:
        st.sidebar.warning("Delete this chat permanently?")
        col_confirm, col_cancel = st.sidebar.columns(2)
        with col_confirm:
            if st.button("Confirm", key="confirm_delete_chat", use_container_width=True):
                delete_conversation(conversation_id=int(pending_delete_id), user_id=user_id)
                if int(pending_delete_id) == st.session_state.current_conversation_id:
                    _switch_to_latest_or_new(user_id)
                st.session_state.pending_delete_conversation_id = None
                st.session_state.rename_target_conversation_id = None
                st.rerun()
        with col_cancel:
            if st.button("Cancel", key="cancel_delete_chat", use_container_width=True):
                st.session_state.pending_delete_conversation_id = None
                st.rerun()

    if not conversations:
        st.sidebar.caption("No previous chats found.")

    for conv in conversations:
        conv_id = int(conv["id"])
        title = conv["title"] or "New Chat"
        trimmed_title = f"{title[:40]}..." if len(title) > 40 else title
        is_current = conv_id == st.session_state.current_conversation_id
        label = f"• {trimmed_title}" if is_current else trimmed_title

        col_open, col_rename, col_delete = st.sidebar.columns([8, 1, 1])
        with col_open:
            if st.button(label, key=f"conv_{conv_id}", use_container_width=True):
                _load_conversation(conv_id)
                st.rerun()
        with col_rename:
            if st.button("✎", key=f"rename_{conv_id}", help="Rename chat", use_container_width=True):
                st.session_state.rename_target_conversation_id = conv_id
                st.session_state.rename_draft_title = title
                st.session_state.pending_delete_conversation_id = None
                st.rerun()
        with col_delete:
            if st.button("🗑", key=f"delete_{conv_id}", help="Delete chat", use_container_width=True):
                st.session_state.pending_delete_conversation_id = conv_id
                st.session_state.rename_target_conversation_id = None
                st.rerun()

    rename_target_id = st.session_state.rename_target_conversation_id
    if rename_target_id is not None:
        st.sidebar.markdown("#### Rename Chat")
        st.session_state.rename_draft_title = st.sidebar.text_input(
            "New title",
            value=st.session_state.rename_draft_title,
            key="rename_chat_input",
        )
        rename_col_save, rename_col_cancel = st.sidebar.columns(2)
        with rename_col_save:
            if st.button("Save", key="save_chat_rename", use_container_width=True):
                try:
                    rename_conversation(
                        conversation_id=int(rename_target_id),
                        user_id=user_id,
                        new_title=st.session_state.rename_draft_title,
                    )
                    st.session_state.rename_target_conversation_id = None
                    st.success("Chat renamed.")
                except ValueError as ve:
                    st.sidebar.error(str(ve))
                st.rerun()
        with rename_col_cancel:
            if st.button("Cancel", key="cancel_chat_rename", use_container_width=True):
                st.session_state.rename_target_conversation_id = None
                st.rerun()

    st.sidebar.divider()
    if st.sidebar.button("Logout", use_container_width=True):
        _reset_auth_state()
        st.rerun()


initialize_db()
bootstrap_admin_user()
_init_session_state()
_enforce_session_timeout()

if not st.session_state.authenticated:
    _render_auth_screen()
    st.stop()

# -- Index check ---------------------------------------------------------------
if not Path(INDEX_PATH).exists():
    st.error(
        "**Vector index not found.**\n\n"
        "Please run the ingestion pipeline first:\n"
        "```\npython build_vectorstore.py\n```"
    )
    st.stop()

# Ensure the selected conversation exists and load history from DB.
_ensure_active_conversation()

_render_sidebar()

# -- Header --------------------------------------------------------------------
col_title, col_btn = st.columns([6, 1])
with col_title:
    st.markdown("## 📘 SAARTHI - Regulatory Q&A Assistant")
with col_btn:
    if st.button("+ New", help="Start a new chat"):
        user_id = int(st.session_state.auth_user["user_id"])
        st.session_state.current_conversation_id = create_conversation(user_id=user_id)
        st.session_state.history = []
        st.rerun()

st.caption(
    "Ask questions grounded in indexed RBI regulatory documents. "
    "SAARTHI automatically detects when to compare versions across circular editions."
)

# -- Model selector ------------------------------------------------------------
with st.expander("🤖 Model Settings", expanded=False):
    col1, col2 = st.columns([1.5, 1])

    with col1:
        model_options = {model["name"]: model["id"] for model in AVAILABLE_MODELS}
        selected_model_name = st.selectbox(
            "Choose AI Model",
            options=list(model_options.keys()),
            index=list(model_options.values()).index(st.session_state.selected_model),
            help="Select based on your computer's capabilities",
        )
        st.session_state.selected_model = model_options[selected_model_name]

    with col2:
        model_config = get_model_by_id(st.session_state.selected_model)
        if model_config:
            st.metric("Current", model_config["label"], delta=model_config["parameters"])

    if model_config:
        st.divider()
        st.markdown(get_model_info_text(model_config))

        st.divider()
        st.subheader("Available Models")
        for model in AVAILABLE_MODELS:
            with st.container():
                col_name, col_ram, col_speed = st.columns([2, 1, 1])
                with col_name:
                    status = "✓ Current" if model["id"] == st.session_state.selected_model else ""
                    st.write(f"**{model['name']}** {model['label']} {status}")
                with col_ram:
                    st.caption(f"RAM: {model['ram_needed']}")
                with col_speed:
                    st.caption(f"Speed: {model['speed']}")

# -- Chat history replay -------------------------------------------------------
for message in st.session_state.history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        sources = message.get("sources")
        if sources:
            _render_sources(sources)

if not st.session_state.history:
    st.markdown(
        '<div class="welcome-card">'
        "<h2>Namaste! I'm SAARTHI 🙏</h2>"
        "<p>Your AI assistant for exploring RBI regulatory guidelines - "
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

question = st.chat_input("Ask SAARTHI a question about RBI regulatory guidelines...")

st.markdown(
    '<div class="disclaimer-bottom">'
    "⚠️ For informational purposes only - refer to the official "
    '<a href="https://www.rbi.org.in" target="_blank">RBI circulars</a> '
    "and consult qualified professionals before making compliance decisions."
    "</div>",
    unsafe_allow_html=True,
)

if question:
    user_id = int(st.session_state.auth_user["user_id"])
    conv_id = int(st.session_state.current_conversation_id)

    st.session_state.history.append({"role": "user", "content": question, "sources": []})
    add_message(
        conversation_id=conv_id,
        user_id=user_id,
        role="user",
        content=question,
        sources=[],
    )

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        predefined = get_predefined_response(question)

        if predefined:
            answer = predefined
            sources = []
            st.markdown(answer)
            is_temporal = False

        elif (is_temporal := detect_temporal_intent(question)):
            with st.spinner("SAARTHI is comparing document versions - this may take a moment..."):
                try:
                    result = ask_temporal_question(
                        question=question,
                        k=TOP_K,
                        model_name=st.session_state.selected_model,
                        comparison_method=COMPARISON_METHOD,
                    )
                except Exception:
                    result = {
                        "fallback": True,
                        "fallback_reason": "exception",
                        "answer": (
                            "**Unable to complete version comparison.**\n\n"
                            "The system encountered an issue while comparing "
                            "document versions. Please verify that Ollama is "
                            "running and the selected model is available, then "
                            "try again."
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

        else:
            with st.spinner("SAARTHI is retrieving relevant sections..."):
                try:
                    result = ask_question(
                        question=question,
                        k=TOP_K,
                        model_name=st.session_state.selected_model,
                    )
                    answer = result["answer"]
                    sources = result["sources"]
                except ConnectionError:
                    answer = (
                        "**Could not connect to the language model.**\n\n"
                        "Please ensure Ollama is running on your machine "
                        f"(`ollama serve`) and the model **{st.session_state.selected_model}** is available "
                        f"(`ollama pull {st.session_state.selected_model}`)."
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
                except Exception:
                    answer = (
                        "**Something went wrong while processing your question.**\n\n"
                        "Please try rephrasing your query or check that Ollama "
                        "is running correctly."
                    )
                    sources = []

            st.markdown(answer)
            if sources:
                _render_sources(sources)

    stored_sources = sources if not is_temporal else []
    st.session_state.history.append(
        {
            "role": "assistant",
            "content": answer,
            "sources": stored_sources,
        }
    )
    add_message(
        conversation_id=conv_id,
        user_id=user_id,
        role="assistant",
        content=answer,
        sources=stored_sources,
    )

st.markdown(
    '<div class="app-footer">'
    "SAARTHI &middot; Regulatory Q&amp;A Assistant &middot; "
    "Secure employee sessions enabled &middot; "
    "Powered by LangChain, FAISS &amp; Ollama"
    "</div>",
    unsafe_allow_html=True,
)
