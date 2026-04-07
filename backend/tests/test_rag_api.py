"""Phase 3 RAG and temporal endpoint tests."""

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


def _auth_headers(client: TestClient, employee_id: str = "EMP4001") -> dict[str, str]:
    password = "SecurePass#123"
    client.post(
        "/api/v1/auth/register",
        json={
            "employee_id": employee_id,
            "full_name": "Rag Tester",
            "password": password,
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"employee_id": employee_id, "password": password},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_models_endpoint_returns_catalog(client: TestClient):
    headers = _auth_headers(client)
    response = client.get("/api/v1/models", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "models" in body["data"]
    assert "recommended_model" in body["data"]


def test_qa_endpoint_success(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4002")

    def fake_ask_question(question: str, k: int, model_name: str) -> dict:
        assert question == "What are KYC requirements?"
        return {
            "answer": "KYC requires customer due diligence.",
            "sources": [
                {
                    "content": "KYC section snippet",
                    "metadata": {"source": "masterdirectionkyc.pdf", "page": 12},
                }
            ],
        }

    monkeypatch.setattr("backend.app.api.routers.rag.ask_question", fake_ask_question)

    response = client.post(
        "/api/v1/chat/ask",
        headers=headers,
        json={"question": "What are KYC requirements?", "model_id": "phi:2.7b", "top_k": 4},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["mode"] == "qa"
    assert body["data"]["answer"]
    assert len(body["data"]["formatted_sources"]) == 1


def test_qa_predefined_path(client: TestClient):
    headers = _auth_headers(client, employee_id="EMP4003")

    response = client.post(
        "/api/v1/chat/ask",
        headers=headers,
        json={"question": "who are you", "top_k": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["mode"] == "predefined"
    assert body["data"]["metadata"]["predefined"] is True


def test_qa_error_mapping_model_unavailable(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4004")

    def fake_ask_question(*args, **kwargs):
        raise ConnectionError("ollama unavailable")

    monkeypatch.setattr("backend.app.api.routers.rag.ask_question", fake_ask_question)

    response = client.post(
        "/api/v1/chat/ask",
        headers=headers,
        json={"question": "Explain KYC", "model_id": "phi:2.7b", "top_k": 4},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "model_unavailable"


def test_qa_invalid_model_maps_to_validation_error(client: TestClient):
    headers = _auth_headers(client, employee_id="EMP4012")

    response = client.post(
        "/api/v1/chat/ask",
        headers=headers,
        json={"question": "Explain KYC", "model_id": "unknown-model", "top_k": 4},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"


def test_qa_rejects_malformed_model_id(client: TestClient):
    headers = _auth_headers(client, employee_id="EMP4013")

    response = client.post(
        "/api/v1/chat/ask",
        headers=headers,
        json={"question": "Explain KYC", "model_id": "bad model!", "top_k": 4},
    )

    assert response.status_code == 422


def test_temporal_endpoint_comparison_path(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4005")

    monkeypatch.setattr("backend.app.api.routers.rag.detect_temporal_intent", lambda question: True)
    monkeypatch.setattr(
        "backend.app.api.routers.rag.ask_temporal_question",
        lambda **kwargs: {
            "fallback": False,
            "single_version": False,
            "comparison": {
                "difflib_result": "- old\n+ new",
                "llm_summary": "Disclosure obligations were expanded.",
            },
            "current_date": "2025-01-01",
            "previous_date": "2022-01-01",
            "document_title": "RBI Digital Lending Guidelines",
        },
    )

    response = client.post(
        "/api/v1/chat/ask-temporal",
        headers=headers,
        json={
            "question": "How has digital lending changed?",
            "model_id": "phi:2.7b",
            "top_k": 5,
            "comparison_method": "both",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["mode"] == "temporal_comparison"
    assert body["data"]["temporal"]["intent_detected"] is True


def test_temporal_endpoint_fallback_and_single_version_paths(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4006")

    monkeypatch.setattr("backend.app.api.routers.rag.detect_temporal_intent", lambda question: True)

    monkeypatch.setattr(
        "backend.app.api.routers.rag.ask_temporal_question",
        lambda **kwargs: {
            "fallback": True,
            "fallback_reason": "no_metadata",
            "answer": "fallback answer",
            "sources": [],
        },
    )
    fallback_resp = client.post(
        "/api/v1/chat/ask-temporal",
        headers=headers,
        json={"question": "Compare updates", "model_id": "phi:2.7b", "top_k": 4, "comparison_method": "both"},
    )
    assert fallback_resp.status_code == 200
    assert fallback_resp.json()["data"]["mode"] == "temporal_fallback"

    monkeypatch.setattr(
        "backend.app.api.routers.rag.ask_temporal_question",
        lambda **kwargs: {
            "fallback": False,
            "single_version": True,
            "document_title": "Doc",
            "current_date": "2025-01-01",
        },
    )
    single_resp = client.post(
        "/api/v1/chat/ask-temporal",
        headers=headers,
        json={"question": "Compare updates", "model_id": "phi:2.7b", "top_k": 4, "comparison_method": "both"},
    )
    assert single_resp.status_code == 200
    assert single_resp.json()["data"]["mode"] == "temporal_single_version"
    assert "Only one version of this document is currently indexed" in single_resp.json()["data"]["answer"]


def test_temporal_non_temporal_query_falls_back_to_qa(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4007")

    monkeypatch.setattr("backend.app.api.routers.rag.detect_temporal_intent", lambda question: False)
    monkeypatch.setattr(
        "backend.app.api.routers.rag.ask_question",
        lambda **kwargs: {"answer": "standard qa", "sources": []},
    )

    response = client.post(
        "/api/v1/chat/ask-temporal",
        headers=headers,
        json={"question": "What is KYC?", "model_id": "phi:2.7b", "top_k": 4, "comparison_method": "both"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["mode"] == "qa_fallback_non_temporal"
    assert body["data"]["temporal"]["intent_detected"] is False


def test_temporal_timeout_error_mapping(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4008")

    monkeypatch.setattr("backend.app.api.routers.rag.detect_temporal_intent", lambda question: True)
    monkeypatch.setattr(
        "backend.app.api.routers.rag.run_with_timeout",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("timed out")),
    )

    response = client.post(
        "/api/v1/chat/ask-temporal",
        headers=headers,
        json={"question": "How changed?", "model_id": "phi:2.7b", "top_k": 4, "comparison_method": "both"},
    )

    assert response.status_code == 504
    body = response.json()
    assert body["error"]["code"] == "request_timeout"
