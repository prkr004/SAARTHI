"""Admin API coverage for approvals, authorization, and ingestion job lifecycle."""

from __future__ import annotations

from pathlib import Path

import chat_store
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_store, "DB_PATH", tmp_path / "saarthi_secure_test.db")
    with TestClient(app) as test_client:
        yield test_client


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "employee_id": chat_store.DEFAULT_ADMIN_EMPLOYEE_ID,
            "password": chat_store.DEFAULT_ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _approved_user_headers(client: TestClient, employee_id: str) -> dict[str, str]:
    password = "SecurePass#123"
    client.post(
        "/api/v1/auth/register",
        json={
            "employee_id": employee_id,
            "full_name": "Regular User",
            "password": password,
            "email": f"{employee_id.lower()}@example.com",
        },
    )
    chat_store.set_user_approval_status(employee_id, chat_store.APPROVAL_APPROVED)
    login = client.post(
        "/api/v1/auth/login",
        json={"employee_id": employee_id, "password": password},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_admin_can_approve_and_reject_user_requests(client: TestClient):
    admin_headers = _admin_headers(client)

    pending_user = {
        "employee_id": "EMP6001",
        "full_name": "Pending Employee",
        "password": "SecurePass#123",
        "email": "pending.user@example.com",
    }
    register_response = client.post("/api/v1/auth/register", json=pending_user)
    assert register_response.status_code == 201

    pending_list = client.get("/api/v1/admin/users/pending", headers=admin_headers)
    assert pending_list.status_code == 200
    pending_ids = {entry["employee_id"] for entry in pending_list.json()}
    assert "EMP6001" in pending_ids

    target_user = next(entry for entry in pending_list.json() if entry["employee_id"] == "EMP6001")
    approve_response = client.post(
        f"/api/v1/admin/users/{target_user['id']}/approve",
        json={"review_reason": "Verified onboarding details"},
        headers=admin_headers,
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["user"]["approval_status"] == "approved"

    approved_login = client.post(
        "/api/v1/auth/login",
        json={"employee_id": "EMP6001", "password": "SecurePass#123"},
    )
    assert approved_login.status_code == 200

    reject_user_payload = {
        "employee_id": "EMP6002",
        "full_name": "Rejected Employee",
        "password": "SecurePass#123",
        "email": "reject.user@example.com",
    }
    reject_register = client.post("/api/v1/auth/register", json=reject_user_payload)
    assert reject_register.status_code == 201

    pending_list_again = client.get("/api/v1/admin/users/pending", headers=admin_headers)
    reject_target = next(entry for entry in pending_list_again.json() if entry["employee_id"] == "EMP6002")

    reject_response = client.post(
        f"/api/v1/admin/users/{reject_target['id']}/reject",
        json={"review_reason": "Missing department approval"},
        headers=admin_headers,
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["user"]["approval_status"] == "rejected"

    blocked_login = client.post(
        "/api/v1/auth/login",
        json={"employee_id": "EMP6002", "password": "SecurePass#123"},
    )
    assert blocked_login.status_code == 403


def test_admin_can_list_active_and_revoke_or_grant_access(client: TestClient):
    admin_headers = _admin_headers(client)

    client.post(
        "/api/v1/auth/register",
        json={
            "employee_id": "EMP6003",
            "full_name": "Active Employee",
            "password": "SecurePass#123",
            "email": "active.employee@example.com",
        },
    )
    chat_store.set_user_approval_status("EMP6003", chat_store.APPROVAL_APPROVED)

    active_response = client.get("/api/v1/admin/users/active", headers=admin_headers)
    assert active_response.status_code == 200
    active_rows = active_response.json()["users"]
    target_row = next(item for item in active_rows if item["employee_id"] == "EMP6003")

    revoke_response = client.post(
        f"/api/v1/admin/users/{target_row['id']}/revoke",
        json={"review_reason": "Access revoked for policy violation"},
        headers=admin_headers,
    )
    assert revoke_response.status_code == 200
    assert revoke_response.json()["user"]["approval_status"] == "rejected"

    blocked_login = client.post(
        "/api/v1/auth/login",
        json={"employee_id": "EMP6003", "password": "SecurePass#123"},
    )
    assert blocked_login.status_code == 403

    grant_response = client.post(
        "/api/v1/admin/users/grant-access",
        json={"employee_id": "EMP6003", "review_reason": "Reinstated by admin"},
        headers=admin_headers,
    )
    assert grant_response.status_code == 200
    assert grant_response.json()["user"]["approval_status"] == "approved"

    restored_login = client.post(
        "/api/v1/auth/login",
        json={"employee_id": "EMP6003", "password": "SecurePass#123"},
    )
    assert restored_login.status_code == 200


def test_admin_endpoints_reject_non_admin_users(client: TestClient):
    user_headers = _approved_user_headers(client, "EMP6101")

    pending_response = client.get("/api/v1/admin/users/pending", headers=user_headers)
    assert pending_response.status_code == 403

    jobs_response = client.get("/api/v1/admin/ingestion/jobs", headers=user_headers)
    assert jobs_response.status_code == 403

    documents_response = client.get("/api/v1/admin/documents", headers=user_headers)
    assert documents_response.status_code == 403

    summary_jobs_response = client.get("/api/v1/admin/summary/jobs", headers=user_headers)
    assert summary_jobs_response.status_code == 403


def test_review_endpoints_surface_notification_warnings(client: TestClient, monkeypatch):
    admin_headers = _admin_headers(client)

    class _StubNotificationService:
        def send_approval_email(self, *, recipient_email: str | None, full_name: str):
            return type("Result", (), {"warning": "SMTP unavailable"})()

        def send_rejection_email(self, *, recipient_email: str | None, full_name: str, review_reason: str | None):
            return type("Result", (), {"warning": "SMTP unavailable"})()

    monkeypatch.setattr("backend.app.api.routers.admin.NotificationService", _StubNotificationService)

    pending_user = {
        "employee_id": "EMP6010",
        "full_name": "Pending Warning",
        "password": "SecurePass#123",
        "email": "pending.warning@example.com",
    }
    register_response = client.post("/api/v1/auth/register", json=pending_user)
    assert register_response.status_code == 201

    pending_list = client.get("/api/v1/admin/users/pending", headers=admin_headers)
    target_user = next(entry for entry in pending_list.json() if entry["employee_id"] == "EMP6010")

    approve_response = client.post(
        f"/api/v1/admin/users/{target_user['id']}/approve",
        json={"review_reason": "OK"},
        headers=admin_headers,
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["warning"] == "SMTP unavailable"


def test_review_endpoints_trigger_notification_dispatch(client: TestClient, monkeypatch):
    admin_headers = _admin_headers(client)

    dispatch_log: list[tuple[str, str | None]] = []

    class _RecordingNotificationService:
        def send_approval_email(self, *, recipient_email: str | None, full_name: str):
            dispatch_log.append(("approved", recipient_email))
            return type("Result", (), {"warning": None})()

        def send_rejection_email(self, *, recipient_email: str | None, full_name: str, review_reason: str | None):
            dispatch_log.append(("rejected", recipient_email))
            return type("Result", (), {"warning": None})()

    monkeypatch.setattr("backend.app.api.routers.admin.NotificationService", _RecordingNotificationService)

    first_user = {
        "employee_id": "EMP6011",
        "full_name": "Approve Candidate",
        "password": "SecurePass#123",
        "email": "approve.candidate@example.com",
    }
    second_user = {
        "employee_id": "EMP6012",
        "full_name": "Reject Candidate",
        "password": "SecurePass#123",
        "email": "reject.candidate@example.com",
    }

    assert client.post("/api/v1/auth/register", json=first_user).status_code == 201
    assert client.post("/api/v1/auth/register", json=second_user).status_code == 201

    pending = client.get("/api/v1/admin/users/pending", headers=admin_headers)
    assert pending.status_code == 200
    rows = pending.json()

    approve_target = next(entry for entry in rows if entry["employee_id"] == "EMP6011")
    reject_target = next(entry for entry in rows if entry["employee_id"] == "EMP6012")

    approve_response = client.post(
        f"/api/v1/admin/users/{approve_target['id']}/approve",
        json={"review_reason": "Approved"},
        headers=admin_headers,
    )
    reject_response = client.post(
        f"/api/v1/admin/users/{reject_target['id']}/reject",
        json={"review_reason": "Rejected"},
        headers=admin_headers,
    )

    assert approve_response.status_code == 200
    assert reject_response.status_code == 200
    assert ("approved", "approve.candidate@example.com") in dispatch_log
    assert ("rejected", "reject.candidate@example.com") in dispatch_log


def test_ingestion_job_lifecycle_transitions(client: TestClient, monkeypatch, tmp_path: Path):
    admin_headers = _admin_headers(client)

    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4\n")

    async def fake_persist_uploaded_pdfs(files):
        assert len(files) == 2
        return [fake_pdf, fake_pdf]

    def fake_start_ingestion_job(*, job_id: str, stored_files):
        assert list(stored_files)
        chat_store.update_ingestion_job(
            job_id,
            status=chat_store.INGESTION_STATUS_RUNNING,
            processed_files=1,
            total_chunks=3,
            progress_percent=50,
            started_at="2026-04-19T00:00:00+00:00",
            current_file="fake.pdf",
        )
        chat_store.update_ingestion_job(
            job_id,
            status=chat_store.INGESTION_STATUS_COMPLETED,
            processed_files=2,
            total_chunks=6,
            progress_percent=100,
            completed_at="2026-04-19T00:00:10+00:00",
            current_file=None,
        )

    monkeypatch.setattr(
        "backend.app.api.routers.admin.persist_uploaded_pdfs",
        fake_persist_uploaded_pdfs,
    )
    monkeypatch.setattr(
        "backend.app.api.routers.admin.start_ingestion_job",
        fake_start_ingestion_job,
    )

    create_response = client.post(
        "/api/v1/admin/ingestion/jobs",
        headers=admin_headers,
        files=[
            ("files", ("doc1.pdf", b"%PDF-1.4\n", "application/pdf")),
            ("files", ("doc2.pdf", b"%PDF-1.4\n", "application/pdf")),
        ],
    )
    assert create_response.status_code == 202

    payload = create_response.json()
    job_id = payload["job"]["job_id"]

    status_response = client.get(f"/api/v1/admin/ingestion/jobs/{job_id}", headers=admin_headers)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "completed"
    assert status_payload["processed_files"] == 2
    assert status_payload["progress_percent"] == 100

    list_response = client.get("/api/v1/admin/ingestion/jobs", headers=admin_headers)
    assert list_response.status_code == 200
    listed_ids = {job["job_id"] for job in list_response.json()["jobs"]}
    assert job_id in listed_ids


def test_backfill_job_lifecycle_transitions(client: TestClient, monkeypatch):
    admin_headers = _admin_headers(client)

    def fake_start_document_backfill_job(*, job_id: str, manifest_path: str | None = None):
        assert manifest_path
        chat_store.update_backfill_job(
            job_id,
            status=chat_store.BACKFILL_STATUS_RUNNING,
            total_documents=3,
            processed_documents=1,
            discovered_chunks=7,
            progress_percent=34,
            started_at="2026-04-20T00:00:00+00:00",
            current_document_key="doc_1",
        )
        chat_store.update_backfill_job(
            job_id,
            status=chat_store.BACKFILL_STATUS_COMPLETED,
            total_documents=3,
            processed_documents=3,
            discovered_chunks=7,
            progress_percent=100,
            completed_at="2026-04-20T00:00:10+00:00",
            current_document_key=None,
        )

    monkeypatch.setattr(
        "backend.app.api.routers.admin.start_document_backfill_job",
        fake_start_document_backfill_job,
    )

    create_response = client.post(
        "/api/v1/admin/backfill/jobs",
        headers=admin_headers,
        json={},
    )
    assert create_response.status_code == 202
    payload = create_response.json()
    job_id = payload["job"]["job_id"]

    status_response = client.get(f"/api/v1/admin/backfill/jobs/{job_id}", headers=admin_headers)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "completed"
    assert status_payload["processed_documents"] == 3
    assert status_payload["discovered_chunks"] == 7
    assert status_payload["progress_percent"] == 100

    list_response = client.get("/api/v1/admin/backfill/jobs", headers=admin_headers)
    assert list_response.status_code == 200
    listed_ids = {job["job_id"] for job in list_response.json()["jobs"]}
    assert job_id in listed_ids


def test_document_registry_admin_endpoints_happy_path(client: TestClient, monkeypatch):
    admin_headers = _admin_headers(client)

    created = chat_store.upsert_document_registry_entry(
        document_key="rbi|doc_registry_happy|2026-04-20",
        source="doc_registry_happy.pdf",
        document_title="Registry Happy Document",
        version_date="2026-04-20",
        effective_date="2026-04-20",
        regulator="RBI",
        document_status="Active",
        chunk_count=4,
        metadata={"source_type": "pdf"},
    )
    document_id = int(created["id"])

    cache_refresh_calls = {"count": 0}
    reindex_calls: list[dict] = []

    def fake_refresh_rag_caches():
        cache_refresh_calls["count"] += 1

    def fake_run_registry_reindex(*, trigger: str, document_id: int | None = None, actor_user_id: int | None = None):
        reindex_calls.append(
            {
                "trigger": trigger,
                "document_id": document_id,
                "actor_user_id": actor_user_id,
            }
        )
        return {
            "success": True,
            "reason": "test_stub",
        }

    monkeypatch.setattr("backend.app.api.routers.admin.refresh_rag_caches", fake_refresh_rag_caches)
    monkeypatch.setattr("backend.app.api.routers.admin.run_registry_reindex", fake_run_registry_reindex)

    list_response = client.get(
        "/api/v1/admin/documents",
        headers=admin_headers,
        params={"summary_status": "pending", "q": "Registry Happy", "limit": 20, "offset": 0},
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert int(list_payload["total"]) >= 1
    assert any(int(item["id"]) == document_id for item in list_payload["documents"])

    detail_response = client.get(f"/api/v1/admin/documents/{document_id}", headers=admin_headers)
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert int(detail_payload["document"]["id"]) == document_id
    assert isinstance(detail_payload["audit_log"], list)

    patch_response = client.patch(
        f"/api/v1/admin/documents/{document_id}",
        headers=admin_headers,
        json={
            "regulator": "Reserve Bank of India",
            "document_status": "Current",
            "chunk_count": 7,
            "metadata": {"source_type": "pdf", "revision": "v2"},
        },
    )
    assert patch_response.status_code == 200
    patch_payload = patch_response.json()
    assert patch_payload["document"]["regulator"] == "Reserve Bank of India"
    assert patch_payload["document"]["document_status"] == "Current"
    assert int(patch_payload["document"]["chunk_count"]) == 7

    delete_response = client.post(
        f"/api/v1/admin/documents/{document_id}/soft-delete",
        headers=admin_headers,
        json={"reason": "Superseded document"},
    )
    assert delete_response.status_code == 200
    delete_payload = delete_response.json()
    assert int(delete_payload["document"]["is_deleted"]) == 1

    deleted_only_response = client.get(
        "/api/v1/admin/documents",
        headers=admin_headers,
        params={"include_deleted": True, "is_deleted": True, "q": "Registry Happy"},
    )
    assert deleted_only_response.status_code == 200
    deleted_documents = deleted_only_response.json()["documents"]
    assert any(int(item["id"]) == document_id for item in deleted_documents)

    assert cache_refresh_calls["count"] >= 2
    assert len(reindex_calls) >= 2
    assert {item["trigger"] for item in reindex_calls} >= {
        "admin_documents_update",
        "admin_documents_soft_delete",
    }
    assert all(int(item["document_id"] or 0) == document_id for item in reindex_calls)


def test_document_registry_admin_endpoints_failure_paths(client: TestClient):
    admin_headers = _admin_headers(client)

    invalid_filter = client.get(
        "/api/v1/admin/documents",
        headers=admin_headers,
        params={"summary_status": "invalid-status"},
    )
    assert invalid_filter.status_code == 400

    missing_detail = client.get("/api/v1/admin/documents/999999", headers=admin_headers)
    assert missing_detail.status_code == 404

    empty_patch = client.patch(
        "/api/v1/admin/documents/999999",
        headers=admin_headers,
        json={},
    )
    assert empty_patch.status_code == 400

    missing_patch = client.patch(
        "/api/v1/admin/documents/999999",
        headers=admin_headers,
        json={"regulator": "RBI"},
    )
    assert missing_patch.status_code == 404

    missing_delete = client.post(
        "/api/v1/admin/documents/999999/soft-delete",
        headers=admin_headers,
        json={"reason": "missing"},
    )
    assert missing_delete.status_code == 404


def test_summary_job_lifecycle_transitions(client: TestClient, monkeypatch):
    admin_headers = _admin_headers(client)

    # Seed at least one pending document so total_documents is non-zero.
    chat_store.upsert_document_registry_entry(
        document_key="rbi|summary_job|2026-04-20",
        source="summary_job.pdf",
        document_title="Summary Job Document",
        version_date="2026-04-20",
        effective_date="2026-04-20",
        regulator="RBI",
        document_status="Active",
        chunk_count=2,
    )

    def fake_start_document_summary_job(*, job_id: str, include_failed: bool, retry_after_seconds: int, batch_size: int):
        assert include_failed is True
        assert retry_after_seconds == 0
        assert batch_size == 10
        chat_store.update_summary_job(
            job_id,
            status=chat_store.SUMMARY_JOB_STATUS_RUNNING,
            total_documents=2,
            processed_documents=1,
            completed_documents=1,
            failed_documents=0,
            started_at="2026-04-20T00:00:00+00:00",
        )
        chat_store.update_summary_job(
            job_id,
            status=chat_store.SUMMARY_JOB_STATUS_COMPLETED,
            total_documents=2,
            processed_documents=2,
            completed_documents=2,
            failed_documents=0,
            completed_at="2026-04-20T00:00:15+00:00",
        )

    monkeypatch.setattr(
        "backend.app.api.routers.admin.start_document_summary_job",
        fake_start_document_summary_job,
    )

    create_response = client.post(
        "/api/v1/admin/summary/jobs",
        headers=admin_headers,
        json={"include_failed": True, "retry_after_seconds": 0, "batch_size": 10},
    )
    assert create_response.status_code == 202

    payload = create_response.json()
    job_id = payload["job"]["job_id"]

    status_response = client.get(f"/api/v1/admin/summary/jobs/{job_id}", headers=admin_headers)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "completed"
    assert status_payload["processed_documents"] == 2
    assert status_payload["completed_documents"] == 2
    assert status_payload["failed_documents"] == 0

    list_response = client.get("/api/v1/admin/summary/jobs", headers=admin_headers)
    assert list_response.status_code == 200
    listed_ids = {job["job_id"] for job in list_response.json()["jobs"]}
    assert job_id in listed_ids


def test_summary_job_failure_paths(client: TestClient):
    admin_headers = _admin_headers(client)

    missing_job = client.get("/api/v1/admin/summary/jobs/missing_job", headers=admin_headers)
    assert missing_job.status_code == 404
