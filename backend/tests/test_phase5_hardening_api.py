"""Phase 5 hardening and end-to-end smoke tests."""

from __future__ import annotations

import chat_store
import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import get_settings
from backend.app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_store, "DB_PATH", tmp_path / "saarthi_secure_test.db")
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def settings_state():
    settings = get_settings()
    original = {
        "readiness_require_vector_index": settings.readiness_require_vector_index,
        "faiss_index_path": settings.faiss_index_path,
        "session_max_active_per_user": settings.session_max_active_per_user,
    }
    yield settings
    settings.readiness_require_vector_index = original["readiness_require_vector_index"]
    settings.faiss_index_path = original["faiss_index_path"]
    settings.session_max_active_per_user = original["session_max_active_per_user"]


def _register_and_login(client: TestClient, employee_id: str, password: str = "SecurePass#123") -> str:
    client.post(
        "/api/v1/auth/register",
        json={
            "employee_id": employee_id,
            "full_name": "Phase Five Tester",
            "password": password,
        },
    )
    chat_store.set_user_approval_status(employee_id, chat_store.APPROVAL_APPROVED)
    login = client.post(
        "/api/v1/auth/login",
        json={"employee_id": employee_id, "password": password},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def test_auth_sanitizes_employee_id_and_full_name(client: TestClient):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "employee_id": "  EMP5001  ",
            "full_name": "  Priya   Sharma  ",
            "password": "SecurePass#123",
        },
    )
    assert response.status_code == 201

    assert chat_store.set_user_approval_status("EMP5001", chat_store.APPROVAL_APPROVED)

    login = client.post(
        "/api/v1/auth/login",
        json={"employee_id": " EMP5001 ", "password": "SecurePass#123"},
    )
    assert login.status_code == 200


def test_session_limit_revokes_oldest_active_tokens(client: TestClient, settings_state):
    settings_state.session_max_active_per_user = 2

    token_1 = _register_and_login(client, "EMP5002")
    token_2 = _register_and_login(client, "EMP5002")
    token_3 = _register_and_login(client, "EMP5002")

    me_1 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_1}"})
    me_2 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_2}"})
    me_3 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_3}"})

    assert me_1.status_code == 401
    assert me_2.status_code == 200
    assert me_3.status_code == 200


def test_readiness_fails_when_vector_index_required_and_missing(client: TestClient, settings_state, tmp_path):
    settings_state.readiness_require_vector_index = True
    settings_state.faiss_index_path = str(tmp_path / "missing.faiss")

    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert "Vector index missing" in response.json()["detail"]


def test_end_to_end_smoke_login_create_chat_ask_receive_answer_with_sources(client: TestClient, monkeypatch):
    token = _register_and_login(client, "EMP5003")
    headers = {"Authorization": f"Bearer {token}"}

    create = client.post("/api/v1/conversations", headers=headers, json={"title": "Phase 5 Smoke"})
    assert create.status_code == 201
    conversation_id = create.json()["id"]

    add_user = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"role": "user", "content": "How has digital lending changed?", "sources": []},
    )
    assert add_user.status_code == 201

    monkeypatch.setattr("backend.app.api.routers.rag.triage_query_intent", lambda question: "timeline_analysis")
    monkeypatch.setattr(
        "backend.app.api.routers.rag.ask_temporal_question",
        lambda **kwargs: {
            "fallback": True,
            "fallback_reason": "insufficient_version_data",
            "answer": "Disclosure and cooling-off provisions changed in the latest guidance.",
            "sources": [
                {
                    "content": "Updated disclosure requirements are now mandatory.",
                    "metadata": {"source": "rbi_digital_lending_2025.pdf", "page": 9},
                }
            ],
        },
    )

    ask = client.post(
        "/api/v1/chat/ask-temporal",
        headers=headers,
        json={
            "question": "How has digital lending changed?",
            "model_id": "phi:2.7b",
            "top_k": 4,
            "comparison_method": "both",
        },
    )
    assert ask.status_code == 200
    ask_payload = ask.json()

    answer = ask_payload["data"]["answer"]
    sources = ask_payload["data"]["formatted_sources"]
    assert answer
    assert len(sources) == 1
    assert sources[0]["document_name"]

    add_assistant = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"role": "assistant", "content": answer, "sources": sources},
    )
    assert add_assistant.status_code == 201

    history = client.get(f"/api/v1/conversations/{conversation_id}/messages", headers=headers)
    assert history.status_code == 200
    messages = history.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert len(messages[1]["sources"]) == 1
