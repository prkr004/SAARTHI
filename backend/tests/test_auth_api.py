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
    }

    register_response = client.post("/api/v1/auth/register", json=register_payload)
    assert register_response.status_code == 201

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

    logout_response = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_response.status_code == 200

    me_after_logout = client.get("/api/v1/auth/me", headers=headers)
    assert me_after_logout.status_code == 401


def test_duplicate_registration_returns_400(client: TestClient):
    payload = {
        "employee_id": "EMP2001",
        "full_name": "Priya Singh",
        "password": "StrongPass#789",
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
