"""
Streamlit UI components for displaying version-comparison results.

All functions receive pre-computed data and render it — no business logic.
"""

from __future__ import annotations

import streamlit as st


def render_change_history(
    comparison: dict,
    current_date: str | None,
    previous_date: str | None,
) -> None:
    """Render a structured change-history panel."""

    # Guard — comparison error
    if "error" in comparison:
        st.warning(
            f"**Version comparison could not be completed.**\n\n{comparison['error']}"
        )
        return

    st.markdown("---")
    st.subheader("📜  Regulatory Change History")

    col_old, col_new = st.columns(2)

    with col_old:
        st.markdown(
            f"**Previous Version** &nbsp;·&nbsp; {previous_date or 'unknown date'}"
        )
        st.text_area(
            "Previous clause",
            value=comparison.get("old_clause", ""),
            height=220,
            disabled=True,
            label_visibility="collapsed",
        )

    with col_new:
        st.markdown(
            f"**Current Version** &nbsp;·&nbsp; {current_date or 'unknown date'}"
        )
        st.text_area(
            "Current clause",
            value=comparison.get("new_clause", ""),
            height=220,
            disabled=True,
            label_visibility="collapsed",
        )

    # Difflib output
    difflib_result = comparison.get("difflib_result")
    if difflib_result:
        with st.expander("🔍  View textual diff", expanded=False):
            st.code(difflib_result, language="diff")

    # LLM summary
    llm_summary = comparison.get("llm_summary")
    if llm_summary:
        with st.expander("🤖  View AI change summary", expanded=True):
            st.markdown(llm_summary)


def render_single_version_notice(
    document_title: str | None,
    version_date: str | None,
) -> None:
    """Friendly notice when only one version is indexed."""
    title = document_title or "this document"
    date = version_date or "unknown"
    st.info(
        f"Only one version of **{title}** (dated {date}) is currently indexed.\n\n"
        "Upload an older or newer version of the same circular to enable "
        "side-by-side change comparison.",
        icon="ℹ️",
    )


def render_no_metadata_notice() -> None:
    """Warn that temporal metadata is missing."""
    st.warning(
        "**Version metadata not found in the current index.**\n\n"
        "The vector store was built without temporal metadata, so change "
        "tracking is unavailable. Re-ingest documents using the metadata-aware "
        "loader (`ingestion/vectorstore_builder.py`) to enable this feature.",
        icon="⚠️",
    )
