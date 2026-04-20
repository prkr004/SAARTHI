"""Phase 1 storage tests for document registry and audit log repository helpers."""

from __future__ import annotations

import sqlite3

import chat_store
import pytest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_store, "DB_PATH", tmp_path / "saarthi_secure_test.db")
    chat_store.initialize_db()
    bootstrap = chat_store.bootstrap_admin_user()
    assert bootstrap.success
    return tmp_path


def test_initialize_db_migrates_legacy_schema_and_preserves_existing_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy_secure.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE ingestion_jobs (
                job_id TEXT PRIMARY KEY,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE RESTRICT
            )
            """
        )

        conn.execute(
            """
            INSERT INTO users (employee_id, full_name, password_hash, created_at)
            VALUES ('EMP9001', 'Legacy User', 'legacy_hash', '2026-04-01T00:00:00+00:00')
            """
        )
        user_id = int(conn.execute("SELECT id FROM users WHERE employee_id = 'EMP9001'").fetchone()[0])

        conn.execute(
            """
            INSERT INTO conversations (user_id, title, created_at, updated_at)
            VALUES (?, 'Legacy Conversation', '2026-04-01T00:00:01+00:00', '2026-04-01T00:00:01+00:00')
            """,
            (user_id,),
        )
        conversation_id = int(conn.execute("SELECT id FROM conversations").fetchone()[0])

        conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, sources_json, created_at)
            VALUES (?, 'user', 'Legacy message', '[]', '2026-04-01T00:00:02+00:00')
            """,
            (conversation_id,),
        )
        conn.execute(
            """
            INSERT INTO ingestion_jobs (job_id, created_by, created_at)
            VALUES ('legacy_job_001', ?, '2026-04-01T00:00:03+00:00')
            """,
            (user_id,),
        )
        conn.commit()

    monkeypatch.setattr(chat_store, "DB_PATH", db_path)

    chat_store.initialize_db()
    chat_store.initialize_db()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        table_names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "documents" in table_names
        assert "document_audit_log" in table_names

        assert int(conn.execute("SELECT COUNT(1) FROM users").fetchone()[0]) == 1
        assert int(conn.execute("SELECT COUNT(1) FROM conversations").fetchone()[0]) == 1
        assert int(conn.execute("SELECT COUNT(1) FROM messages").fetchone()[0]) == 1
        assert int(conn.execute("SELECT COUNT(1) FROM ingestion_jobs").fetchone()[0]) == 1

        document_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(documents)").fetchall()
        }
        assert {
            "document_key",
            "summary_status",
            "summary_one_liner",
            "summary_short",
            "summary_error",
            "summary_updated_at",
            "is_deleted",
            "deleted_at",
            "deleted_by",
            "deleted_reason",
            "metadata_json",
        }.issubset(document_columns)

        audit_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(document_audit_log)").fetchall()
        }
        assert {
            "document_id",
            "event_type",
            "reason",
            "payload_json",
            "actor_user_id",
            "created_at",
        }.issubset(audit_columns)


def test_document_registry_repository_end_to_end(isolated_db):
    admin = chat_store.get_user_by_employee_id(chat_store.DEFAULT_ADMIN_EMPLOYEE_ID)
    assert admin is not None
    admin_id = int(admin["id"])

    created = chat_store.upsert_document_registry_entry(
        document_key="rbi|digital_lending|2024-01-01",
        source="digital_lending_2024.pdf",
        document_title="Digital Lending Guidelines",
        version_date="2024-01-01",
        effective_date="2024-01-01",
        regulator="RBI",
        document_status="Active",
        chunk_count=4,
        metadata={"source_type": "pdf", "language": "en"},
        actor_user_id=admin_id,
        audit_reason="Initial backfill seed",
    )

    document_id = int(created["id"])
    assert created["summary_status"] == chat_store.DOCUMENT_SUMMARY_STATUS_PENDING
    assert int(created["is_deleted"]) == 0

    by_id = chat_store.get_document_by_id(document_id)
    by_key = chat_store.get_document_by_key("rbi|digital_lending|2024-01-01")
    assert by_id is not None
    assert by_key is not None
    assert int(by_id["id"]) == document_id
    assert int(by_key["id"]) == document_id

    listed = chat_store.list_documents()
    assert len(listed) == 1
    assert int(listed[0]["id"]) == document_id

    updated_metadata = chat_store.update_document_registry_metadata(
        document_id,
        document_title="Digital Lending Guidelines (Revised)",
        regulator="Reserve Bank of India",
        document_status="Current",
        chunk_count=9,
        metadata={"source_type": "pdf", "language": "en", "revision": "v2"},
        actor_user_id=admin_id,
        audit_reason="Metadata reconciliation",
    )
    assert updated_metadata is True

    updated_doc = chat_store.get_document_by_id(document_id)
    assert updated_doc is not None
    assert updated_doc["document_title"] == "Digital Lending Guidelines (Revised)"
    assert updated_doc["regulator"] == "Reserve Bank of India"
    assert updated_doc["document_status"] == "Current"
    assert int(updated_doc["chunk_count"]) == 9
    assert updated_doc["metadata"] == {
        "source_type": "pdf",
        "language": "en",
        "revision": "v2",
    }

    assert chat_store.update_document_summary(
        document_id,
        summary_status=chat_store.DOCUMENT_SUMMARY_STATUS_RUNNING,
        actor_user_id=admin_id,
        audit_reason="Summary job started",
    )
    assert chat_store.update_document_summary(
        document_id,
        summary_status=chat_store.DOCUMENT_SUMMARY_STATUS_COMPLETED,
        summary_one_liner="Updated digital lending obligations and disclosure controls.",
        summary_short="This version strengthens borrower disclosures and operational controls.",
        summary_error=None,
        actor_user_id=admin_id,
        audit_reason="Summary job completed",
    )

    summarized = chat_store.get_document_by_id(document_id)
    assert summarized is not None
    assert summarized["summary_status"] == chat_store.DOCUMENT_SUMMARY_STATUS_COMPLETED
    assert summarized["summary_one_liner"]
    assert summarized["summary_short"]
    assert summarized["summary_updated_at"]

    manual_audit_id = chat_store.append_document_audit_log(
        document_id,
        "manual_note",
        actor_user_id=admin_id,
        reason="Operator noted manual verification",
        payload={"ticket": "PHASE1-42"},
    )
    assert manual_audit_id > 0

    audit_rows = chat_store.list_document_audit_log(document_id)
    event_types = {row["event_type"] for row in audit_rows}
    assert chat_store.DOCUMENT_AUDIT_EVENT_UPSERT_CREATED in event_types
    assert chat_store.DOCUMENT_AUDIT_EVENT_METADATA_UPDATED in event_types
    assert chat_store.DOCUMENT_AUDIT_EVENT_SUMMARY_UPDATED in event_types
    assert "manual_note" in event_types

    assert chat_store.soft_delete_document(
        document_id,
        deleted_by=admin_id,
        deleted_reason="Removed by admin for superseded circular",
        actor_user_id=admin_id,
    )

    assert chat_store.get_document_by_id(document_id) is None

    deleted_doc = chat_store.get_document_by_id(document_id, include_deleted=True)
    assert deleted_doc is not None
    assert int(deleted_doc["is_deleted"]) == 1
    assert deleted_doc["deleted_reason"] == "Removed by admin for superseded circular"

    assert chat_store.list_documents() == []
    include_deleted = chat_store.list_documents(include_deleted=True)
    assert len(include_deleted) == 1
    assert int(include_deleted[0]["id"]) == document_id

    resurrected = chat_store.upsert_document_registry_entry(
        document_key="rbi|digital_lending|2024-01-01",
        source="digital_lending_2024.pdf",
        document_title="Digital Lending Guidelines (Revised)",
        version_date="2024-01-01",
        effective_date="2024-01-01",
        regulator="Reserve Bank of India",
        document_status="Current",
        chunk_count=11,
        metadata={"source_type": "pdf", "language": "en", "revision": "v3"},
        actor_user_id=admin_id,
        audit_reason="Reintroduced during reconciliation",
    )

    assert int(resurrected["id"]) == document_id
    assert int(resurrected["is_deleted"]) == 0
    assert resurrected["deleted_at"] is None
    assert resurrected["deleted_by"] is None
    assert resurrected["deleted_reason"] is None


def test_document_registry_validation_and_error_paths(isolated_db):
    created = chat_store.upsert_document_registry_entry(
        source="kyc_master_direction.pdf",
        document_title="Master Direction on KYC",
        version_date="2023-01-01",
    )
    document_id = int(created["id"])

    with pytest.raises(ValueError, match="Invalid document summary status"):
        chat_store.update_document_summary(document_id, summary_status="unknown_status")

    with pytest.raises(ValueError, match="Invalid document summary status"):
        chat_store.list_documents(summary_status="invalid")

    with pytest.raises(LookupError, match="Document not found"):
        chat_store.append_document_audit_log(999999, "manual_note")

    assert chat_store.update_document_registry_metadata(document_id) is False
    assert chat_store.update_document_summary(document_id) is False

    assert chat_store.soft_delete_document(document_id) is True
    assert chat_store.soft_delete_document(document_id) is False


def test_summary_job_repository_helpers_and_candidate_counting(isolated_db):
    admin = chat_store.get_user_by_employee_id(chat_store.DEFAULT_ADMIN_EMPLOYEE_ID)
    assert admin is not None
    admin_id = int(admin["id"])

    pending_doc = chat_store.upsert_document_registry_entry(
        document_key="rbi|summary_pending|2026-04-20",
        source="summary_pending.pdf",
        document_title="Summary Pending",
        version_date="2026-04-20",
    )
    failed_doc = chat_store.upsert_document_registry_entry(
        document_key="rbi|summary_failed|2026-04-20",
        source="summary_failed.pdf",
        document_title="Summary Failed",
        version_date="2026-04-20",
    )
    failed_doc_id = int(failed_doc["id"])

    assert chat_store.update_document_summary(
        failed_doc_id,
        summary_status=chat_store.DOCUMENT_SUMMARY_STATUS_FAILED,
        summary_error="transient failure",
        actor_user_id=admin_id,
    )

    created = chat_store.create_summary_job(
        created_by=admin_id,
        include_failed=True,
        retry_after_seconds=60,
        batch_size=25,
        total_documents=2,
    )
    job_id = str(created["job_id"])

    assert created["status"] == chat_store.SUMMARY_JOB_STATUS_QUEUED
    assert created["include_failed"] is True
    assert created["retry_after_seconds"] == 60
    assert created["batch_size"] == 25

    assert chat_store.update_summary_job(
        job_id,
        status=chat_store.SUMMARY_JOB_STATUS_RUNNING,
        processed_documents=1,
        completed_documents=1,
        failed_documents=0,
        current_document_id=int(pending_doc["id"]),
    )

    reloaded = chat_store.get_summary_job(job_id)
    assert reloaded is not None
    assert reloaded["status"] == chat_store.SUMMARY_JOB_STATUS_RUNNING
    assert reloaded["processed_documents"] == 1
    assert reloaded["current_document_id"] == int(pending_doc["id"])

    listed = chat_store.list_recent_summary_jobs(limit=20)
    assert any(str(item["job_id"]) == job_id for item in listed)

    assert chat_store.update_summary_job(job_id) is False
    with pytest.raises(ValueError, match="Invalid summary job status"):
        chat_store.update_summary_job(job_id, status="invalid")

    # Pending documents are always eligible.
    assert chat_store.count_documents_for_summary(include_failed=False, retry_after_seconds=300) == 1
    # Recent failures are gated by retry_after_seconds.
    assert chat_store.count_documents_for_summary(include_failed=True, retry_after_seconds=3600) == 1
    # Failed documents become eligible with immediate retry.
    assert chat_store.count_documents_for_summary(include_failed=True, retry_after_seconds=0) == 2
