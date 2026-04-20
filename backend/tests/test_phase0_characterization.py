"""Phase 0 characterization tests for baseline contract safety."""

from __future__ import annotations

import chat_store
import pytest

from backend.app.api.routers.rag import _format_sources
from query import format_source_label


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_store, "DB_PATH", tmp_path / "saarthi_secure_test.db")
    chat_store.initialize_db()
    bootstrap = chat_store.bootstrap_admin_user()
    assert bootstrap.success
    return tmp_path


def _create_approved_user(employee_id: str) -> int:
    registration = chat_store.register_user(
        employee_id=employee_id,
        full_name="Phase Zero Tester",
        password="SecurePass#123",
        email=f"{employee_id.lower()}@example.com",
    )
    assert registration.success
    assert chat_store.set_user_approval_status(employee_id, chat_store.APPROVAL_APPROVED)

    user = chat_store.get_user_by_employee_id(employee_id)
    assert user is not None
    return int(user["id"])


def test_auth_contract_pending_then_rejected_with_reason(isolated_db):
    registration = chat_store.register_user(
        employee_id="EMP9101",
        full_name="Approval Contract User",
        password="SecurePass#123",
        email="approval.contract@example.com",
    )
    assert registration.success

    pending = chat_store.authenticate_user("EMP9101", "SecurePass#123")
    assert pending.success is False
    assert pending.approval_status == chat_store.APPROVAL_PENDING
    assert pending.message == chat_store.PENDING_LOGIN_MESSAGE

    assert chat_store.set_user_approval_status(
        "EMP9101",
        chat_store.APPROVAL_REJECTED,
        review_reason="Missing department clearance",
    )
    rejected = chat_store.authenticate_user("EMP9101", "SecurePass#123")

    assert rejected.success is False
    assert rejected.approval_status == chat_store.APPROVAL_REJECTED
    assert "Reason: Missing department clearance" in rejected.message


def test_chat_persistence_contract_first_user_message_sets_title_and_sources_roundtrip(isolated_db):
    user_id = _create_approved_user("EMP9102")
    conversation_id = chat_store.create_conversation(user_id=user_id, title="New Chat")

    first_prompt = "  Please summarize the latest digital lending update with actionable controls.  "
    chat_store.add_message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="user",
        content=first_prompt,
        sources=[],
    )

    assistant_sources = [
        {
            "content": "Key excerpt",
            "metadata": {"source": "digital_lending_2025.pdf", "page": 9},
        }
    ]
    chat_store.add_message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="assistant",
        content="Here are the latest control updates.",
        sources=assistant_sources,
    )

    conversations = chat_store.list_conversations(user_id=user_id)
    row = next(item for item in conversations if int(item["id"]) == conversation_id)
    assert row["title"] == first_prompt.strip()[:80]
    assert int(row["message_count"]) == 2

    messages = chat_store.get_messages(conversation_id=conversation_id, user_id=user_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["sources"] == assistant_sources


def test_ingestion_job_contract_clamps_updates_and_supports_noop(isolated_db):
    admin = chat_store.get_user_by_employee_id(chat_store.DEFAULT_ADMIN_EMPLOYEE_ID)
    assert admin is not None

    job = chat_store.create_ingestion_job(created_by=int(admin["id"]), total_files=2)
    job_id = str(job["job_id"])

    # No kwargs should remain a no-op and return False.
    assert chat_store.update_ingestion_job(job_id) is False

    updated = chat_store.update_ingestion_job(
        job_id,
        status=chat_store.INGESTION_STATUS_RUNNING,
        processed_files=-3,
        total_chunks=-8,
        progress_percent=145,
        current_file="batch_1.pdf",
        error_message=None,
    )
    assert updated is True

    reloaded = chat_store.get_ingestion_job(job_id)
    assert reloaded is not None
    assert reloaded["status"] == chat_store.INGESTION_STATUS_RUNNING
    assert int(reloaded["processed_files"]) == 0
    assert int(reloaded["total_chunks"]) == 0
    assert int(reloaded["progress_percent"]) == 100
    assert reloaded["current_file"] == "batch_1.pdf"
    assert reloaded["error_message"] is None


def test_ingestion_job_contract_recent_jobs_ordered_newest_first(isolated_db):
    admin = chat_store.get_user_by_employee_id(chat_store.DEFAULT_ADMIN_EMPLOYEE_ID)
    assert admin is not None
    admin_id = int(admin["id"])

    first_job = chat_store.create_ingestion_job(created_by=admin_id, total_files=1)
    second_job = chat_store.create_ingestion_job(created_by=admin_id, total_files=1)

    recent = chat_store.list_recent_ingestion_jobs(limit=2)
    recent_ids = [str(entry["job_id"]) for entry in recent]

    assert recent_ids == [str(second_job["job_id"]), str(first_job["job_id"])]


def test_source_formatting_contract_label_mapping_and_snippet_truncation():
    known_name, known_link, known_page = format_source_label(
        {"source": "C:/docs/digital_lending_2025.pdf", "page": 7}
    )
    assert "Digital Lending" in known_name
    assert known_link is not None
    assert known_link.startswith("https://")
    assert known_page == 7

    fallback_name, fallback_link, fallback_page = format_source_label(
        {
            "source": "C:/docs/uploaded_policy_A1B2C3D4E5F60718293A.pdf",
            "page": None,
        }
    )
    assert fallback_name == "uploaded_policy"
    assert fallback_link is None
    assert fallback_page is None

    long_snippet = "A" * 800
    formatted = _format_sources(
        [
            {
                "content": long_snippet,
                "metadata": {"source": "masterdirectionkyc.pdf", "page": 2},
            }
        ]
    )

    assert len(formatted) == 1
    item = formatted[0]
    assert item["document_name"] == "RBI Master Direction on KYC"
    assert item["document_link"] is not None
    assert item["page"] == 2
    assert len(item["snippet"]) == 600
    assert item["snippet"] == long_snippet[:600]