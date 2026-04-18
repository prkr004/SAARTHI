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
