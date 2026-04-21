"""Phase 2 conversation and message API tests."""

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


def _auth_headers(client: TestClient, employee_id: str, full_name: str) -> dict[str, str]:
    password = "SecurePass#123"
    register_payload = {
        "employee_id": employee_id,
        "full_name": full_name,
        "password": password,
        "email": f"{employee_id.lower()}@example.com",
    }
    client.post("/api/v1/auth/register", json=register_payload)
    chat_store.set_user_approval_status(employee_id, chat_store.APPROVAL_APPROVED)
    login_response = client.post(
        "/api/v1/auth/login",
        json={"employee_id": employee_id, "password": password},
    )
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_auth_headers(client: TestClient) -> dict[str, str]:
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "employee_id": chat_store.DEFAULT_ADMIN_EMPLOYEE_ID,
            "password": chat_store.DEFAULT_ADMIN_PASSWORD,
        },
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_conversation_message_flow(client: TestClient):
    headers = _auth_headers(client, employee_id="EMP3001", full_name="Anita Rao")

    default_response = client.post("/api/v1/conversations/default", headers=headers)
    assert default_response.status_code == 200
    default_id = default_response.json()["conversation_id"]

    list_response = client.get("/api/v1/conversations", headers=headers)
    assert list_response.status_code == 200
    assert any(item["id"] == default_id for item in list_response.json())

    create_response = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Regulatory Delta Analysis"},
    )
    assert create_response.status_code == 201
    conversation_id = create_response.json()["id"]

    rename_response = client.patch(
        f"/api/v1/conversations/{conversation_id}",
        headers=headers,
        json={"new_title": "Regulatory Delta Analysis V2"},
    )
    assert rename_response.status_code == 200

    add_user_message = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"role": "user", "content": "What changed in digital lending guidance?", "sources": []},
    )
    assert add_user_message.status_code == 201

    add_assistant_message = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={
            "role": "assistant",
            "content": "There are updates in disclosures and cooling-off rules.",
            "sources": [{"content": "snippet", "metadata": {"page": 2}}],
        },
    )
    assert add_assistant_message.status_code == 201

    messages_response = client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"

    delete_response = client.delete(
        f"/api/v1/conversations/{conversation_id}",
        headers=headers,
    )
    assert delete_response.status_code == 200


def test_list_conversations_requires_auth(client: TestClient):
    response = client.get("/api/v1/conversations")
    assert response.status_code == 401


def test_create_conversation_invalid_title_returns_422(client: TestClient):
    headers = _auth_headers(client, employee_id="EMP3002", full_name="Rahul Jain")
    response = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "    "},
    )
    assert response.status_code == 422


def test_default_conversation_requires_auth(client: TestClient):
    response = client.post("/api/v1/conversations/default")
    assert response.status_code == 401


def test_rename_conversation_denies_non_owner(client: TestClient):
    owner_headers = _auth_headers(client, employee_id="EMP3003", full_name="Owner User")
    other_headers = _auth_headers(client, employee_id="EMP3004", full_name="Other User")

    create_response = client.post(
        "/api/v1/conversations",
        headers=owner_headers,
        json={"title": "Owner Chat"},
    )
    conversation_id = create_response.json()["id"]

    rename_response = client.patch(
        f"/api/v1/conversations/{conversation_id}",
        headers=other_headers,
        json={"new_title": "Not Allowed"},
    )
    assert rename_response.status_code == 403


def test_delete_conversation_denies_non_owner(client: TestClient):
    owner_headers = _auth_headers(client, employee_id="EMP3005", full_name="Delete Owner")
    other_headers = _auth_headers(client, employee_id="EMP3006", full_name="Delete Other")

    create_response = client.post(
        "/api/v1/conversations",
        headers=owner_headers,
        json={"title": "Delete Me"},
    )
    conversation_id = create_response.json()["id"]

    delete_response = client.delete(
        f"/api/v1/conversations/{conversation_id}",
        headers=other_headers,
    )
    assert delete_response.status_code == 403


def test_get_messages_denies_non_owner(client: TestClient):
    owner_headers = _auth_headers(client, employee_id="EMP3007", full_name="Msg Owner")
    other_headers = _auth_headers(client, employee_id="EMP3008", full_name="Msg Other")

    create_response = client.post(
        "/api/v1/conversations",
        headers=owner_headers,
        json={"title": "Private Thread"},
    )
    conversation_id = create_response.json()["id"]

    response = client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=other_headers,
    )
    assert response.status_code == 403


def test_add_message_invalid_role_returns_422(client: TestClient):
    headers = _auth_headers(client, employee_id="EMP3009", full_name="Role Tester")

    create_response = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Role Test Chat"},
    )
    conversation_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"role": "system", "content": "invalid role", "sources": []},
    )
    assert response.status_code == 422


def test_add_message_denies_non_owner(client: TestClient):
    owner_headers = _auth_headers(client, employee_id="EMP3010", full_name="Owner Sender")
    other_headers = _auth_headers(client, employee_id="EMP3011", full_name="Other Sender")

    create_response = client.post(
        "/api/v1/conversations",
        headers=owner_headers,
        json={"title": "Protected Chat"},
    )
    conversation_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=other_headers,
        json={"role": "user", "content": "Attempted unauthorized message", "sources": []},
    )
    assert response.status_code == 403


def test_admin_conversation_flow_uses_admin_scope_store(client: TestClient):
    headers = _admin_auth_headers(client)

    create_response = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "Admin Scope Chat"},
    )
    assert create_response.status_code == 201
    conversation_id = create_response.json()["id"]

    add_response = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"role": "user", "content": "Admin prompt", "sources": []},
    )
    assert add_response.status_code == 201

    list_response = client.get("/api/v1/conversations", headers=headers)
    assert list_response.status_code == 200
    assert any(item["id"] == conversation_id for item in list_response.json())
