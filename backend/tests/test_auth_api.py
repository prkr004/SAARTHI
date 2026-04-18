"""Phase 1 auth API tests."""

from __future__ import annotations

import chat_store
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_store, "DB_PATH", tmp_path / "saarthi_secure_test.db")
    with TestClient(app) as test_client:
        yield test_client


def test_register_login_me_logout_flow(client: TestClient):
    register_payload = {
        "employee_id": "EMP1001",
        "full_name": "Aman Sharma",
        "password": "SecurePass#123",
        "email": "aman.sharma@example.com",
    }

    register_response = client.post("/api/v1/auth/register", json=register_payload)
    assert register_response.status_code == 201
    assert register_response.json()["message"] == (
        "Your request has been sent to the admin. Once approved, you will have access to SAARTHI!"
    )

    pending_login_response = client.post(
        "/api/v1/auth/login",
        json={"employee_id": "EMP1001", "password": "SecurePass#123"},
    )
    assert pending_login_response.status_code == 403

    assert chat_store.set_user_approval_status("EMP1001", chat_store.APPROVAL_APPROVED)

    login_response = client.post(
        "/api/v1/auth/login",
        json={"employee_id": "EMP1001", "password": "SecurePass#123"},
    )
    assert login_response.status_code == 200

    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_response = client.get("/api/v1/auth/me", headers=headers)
    assert me_response.status_code == 200
    me_payload = me_response.json()
    assert me_payload["employee_id"] == "EMP1001"
    assert me_payload["approval_status"] == "approved"
    assert me_payload["role"] == "user"
    assert me_payload["email"] == "aman.sharma@example.com"

    logout_response = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_response.status_code == 200

    me_after_logout = client.get("/api/v1/auth/me", headers=headers)
    assert me_after_logout.status_code == 401


def test_duplicate_registration_returns_400(client: TestClient):
    payload = {
        "employee_id": "EMP2001",
        "full_name": "Priya Singh",
        "password": "StrongPass#789",
        "email": "priya@example.com",
    }

    first = client.post("/api/v1/auth/register", json=payload)
    second = client.post("/api/v1/auth/register", json=payload)

    assert first.status_code == 201
    assert second.status_code == 400


def test_invalid_login_returns_401(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"employee_id": "NO_USER", "password": "wrong"},
    )
    assert response.status_code == 401


def test_rejected_user_login_is_blocked_with_clear_message(client: TestClient):
    payload = {
        "employee_id": "EMP2002",
        "full_name": "Rejected User",
        "password": "StrongPass#789",
        "email": "rejected@example.com",
    }
    register_response = client.post("/api/v1/auth/register", json=payload)
    assert register_response.status_code == 201

    assert chat_store.set_user_approval_status(
        "EMP2002",
        chat_store.APPROVAL_REJECTED,
        review_reason="Insufficient onboarding details",
    )

    login_response = client.post(
        "/api/v1/auth/login",
        json={"employee_id": "EMP2002", "password": "StrongPass#789"},
    )
    assert login_response.status_code == 403
    assert "rejected" in login_response.json()["detail"].lower()


def test_register_requires_email(client: TestClient):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "employee_id": "EMP2010",
            "full_name": "No Email User",
            "password": "StrongPass#789",
        },
    )
    assert response.status_code == 422


def test_admin_and_employee_sessions_can_coexist(client: TestClient):
    register_payload = {
        "employee_id": "EMP2011",
        "full_name": "Coexist User",
        "password": "StrongPass#789",
        "email": "coexist.user@example.com",
    }
    register_response = client.post("/api/v1/auth/register", json=register_payload)
    assert register_response.status_code == 201
    assert chat_store.set_user_approval_status("EMP2011", chat_store.APPROVAL_APPROVED)

    employee_login = client.post(
        "/api/v1/auth/login",
        json={"employee_id": "EMP2011", "password": "StrongPass#789"},
    )
    assert employee_login.status_code == 200
    employee_token = employee_login.json()["access_token"]

    admin_login = client.post(
        "/api/v1/auth/login",
        json={
            "employee_id": chat_store.DEFAULT_ADMIN_EMPLOYEE_ID,
            "password": chat_store.DEFAULT_ADMIN_PASSWORD,
        },
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]

    employee_me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    admin_me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert employee_me.status_code == 200
    assert admin_me.status_code == 200
    assert employee_me.json()["role"] == "user"
    assert admin_me.json()["role"] == "admin"
