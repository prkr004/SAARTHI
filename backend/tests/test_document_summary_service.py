"""Document summary worker tests for transitions, retries, and resilience."""

from __future__ import annotations

import chat_store
import pytest

from backend.app.services import document_summary_service


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_store, "DB_PATH", tmp_path / "saarthi_secure_test.db")
    chat_store.initialize_db()
    bootstrap = chat_store.bootstrap_admin_user()
    assert bootstrap.success
    return tmp_path


def _create_document(*, document_key: str, metadata: dict | None = None) -> dict:
    return chat_store.upsert_document_registry_entry(
        document_key=document_key,
        source=f"{document_key.replace('|', '_')}.pdf",
        document_title=f"Title {document_key}",
        version_date="2026-04-20",
        effective_date="2026-04-20",
        regulator="RBI",
        document_status="Active",
        chunk_count=3,
        metadata=metadata,
    )


def test_summary_worker_transitions_pending_to_completed(isolated_db):
    created = _create_document(document_key="rbi|doc_a|2026-04-20")

    stats = document_summary_service.run_document_summarization_once(
        batch_size=10,
        include_failed=True,
        retry_after_seconds=0,
    )

    assert stats.claimed_documents == 1
    assert stats.completed_documents == 1
    assert stats.failed_documents == 0

    stored = chat_store.get_document_by_id(int(created["id"]))
    assert stored is not None
    assert stored["summary_status"] == chat_store.DOCUMENT_SUMMARY_STATUS_COMPLETED
    assert stored["summary_one_liner"]
    assert stored["summary_short"]
    assert stored["summary_error"] is None


def test_summary_worker_retries_failed_documents(isolated_db, monkeypatch):
    created = _create_document(document_key="rbi|doc_retry|2026-04-20")
    calls = {"count": 0}

    def flaky_generator(document):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary summary outage")
        return ("Recovered one-liner", "Recovered paragraph summary.")

    monkeypatch.setattr(document_summary_service, "generate_document_summaries", flaky_generator)

    first = document_summary_service.run_document_summarization_once(
        batch_size=1,
        include_failed=True,
        retry_after_seconds=0,
    )
    assert first.claimed_documents == 1
    assert first.completed_documents == 0
    assert first.failed_documents == 1

    after_first = chat_store.get_document_by_id(int(created["id"]))
    assert after_first is not None
    assert after_first["summary_status"] == chat_store.DOCUMENT_SUMMARY_STATUS_FAILED
    assert "temporary summary outage" in str(after_first["summary_error"])

    second = document_summary_service.run_document_summarization_once(
        batch_size=1,
        include_failed=True,
        retry_after_seconds=0,
    )
    assert second.claimed_documents == 1
    assert second.completed_documents == 1
    assert second.failed_documents == 0

    after_second = chat_store.get_document_by_id(int(created["id"]))
    assert after_second is not None
    assert after_second["summary_status"] == chat_store.DOCUMENT_SUMMARY_STATUS_COMPLETED
    assert after_second["summary_one_liner"] == "Recovered one-liner"
    assert after_second["summary_short"] == "Recovered paragraph summary."
    assert after_second["summary_error"] is None
    assert calls["count"] == 2


def test_summary_worker_handles_partial_failures_without_stopping_batch(isolated_db):
    failed_doc = _create_document(
        document_key="rbi|doc_fail|2026-04-20",
        metadata={"force_summary_failure": True},
    )
    completed_doc = _create_document(document_key="rbi|doc_ok|2026-04-20")

    stats = document_summary_service.run_document_summarization_once(
        batch_size=2,
        include_failed=False,
        retry_after_seconds=0,
    )

    assert stats.claimed_documents == 2
    assert stats.completed_documents == 1
    assert stats.failed_documents == 1

    failed_state = chat_store.get_document_by_id(int(failed_doc["id"]))
    completed_state = chat_store.get_document_by_id(int(completed_doc["id"]))

    assert failed_state is not None
    assert completed_state is not None

    assert failed_state["summary_status"] == chat_store.DOCUMENT_SUMMARY_STATUS_FAILED
    assert "Forced summary failure" in str(failed_state["summary_error"])

    assert completed_state["summary_status"] == chat_store.DOCUMENT_SUMMARY_STATUS_COMPLETED
    assert completed_state["summary_one_liner"]
    assert completed_state["summary_short"]


def test_summary_worker_recovers_running_documents_after_restart(isolated_db):
    created = _create_document(document_key="rbi|doc_resume|2026-04-20")
    claimed = chat_store.claim_next_document_for_summary(
        include_failed=False,
        retry_after_seconds=0,
    )

    assert claimed is not None
    running_state = chat_store.get_document_by_id(int(created["id"]))
    assert running_state is not None
    assert running_state["summary_status"] == chat_store.DOCUMENT_SUMMARY_STATUS_RUNNING

    recovered_count = document_summary_service.recover_interrupted_document_summaries()
    assert recovered_count == 1

    recovered_state = chat_store.get_document_by_id(int(created["id"]))
    assert recovered_state is not None
    assert recovered_state["summary_status"] == chat_store.DOCUMENT_SUMMARY_STATUS_PENDING
    assert "queued for retry" in str(recovered_state["summary_error"])

    stats = document_summary_service.run_document_summarization_once(
        batch_size=1,
        include_failed=False,
        retry_after_seconds=0,
    )
    assert stats.completed_documents == 1

    final_state = chat_store.get_document_by_id(int(created["id"]))
    assert final_state is not None
    assert final_state["summary_status"] == chat_store.DOCUMENT_SUMMARY_STATUS_COMPLETED


def test_admin_summary_job_updates_progress_and_history(isolated_db, monkeypatch):
    _create_document(document_key="rbi|job_doc_1|2026-04-20")
    _create_document(document_key="rbi|job_doc_2|2026-04-20")

    admin = chat_store.get_user_by_employee_id(chat_store.DEFAULT_ADMIN_EMPLOYEE_ID)
    assert admin is not None

    refresh_calls = {"count": 0}

    def fake_refresh_rag_caches():
        refresh_calls["count"] += 1

    monkeypatch.setattr(document_summary_service, "refresh_rag_caches", fake_refresh_rag_caches)

    created_job = chat_store.create_summary_job(
        created_by=int(admin["id"]),
        include_failed=True,
        retry_after_seconds=0,
        batch_size=10,
        total_documents=2,
    )

    document_summary_service.start_document_summary_job(
        job_id=str(created_job["job_id"]),
        include_failed=True,
        retry_after_seconds=0,
        batch_size=10,
    )

    reloaded = chat_store.get_summary_job(str(created_job["job_id"]))
    assert reloaded is not None
    assert reloaded["status"] == chat_store.SUMMARY_JOB_STATUS_COMPLETED
    assert reloaded["processed_documents"] == 2
    assert reloaded["completed_documents"] == 2
    assert reloaded["failed_documents"] == 0
    assert reloaded["completed_at"]

    docs = chat_store.list_documents_for_admin(limit=10)
    assert all(doc["summary_status"] == chat_store.DOCUMENT_SUMMARY_STATUS_COMPLETED for doc in docs)

    assert refresh_calls["count"] == 1
