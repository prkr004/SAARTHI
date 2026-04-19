"""Phase 3 RAG and temporal endpoint tests."""

from __future__ import annotations

import chat_store
import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from temporal.intent_detector import triage_query_intent

from backend.app.main import app
from backend.app.services.circular_linking_service import resolve_circular_links


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
            "email": f"{employee_id.lower()}@example.com",
        },
    )
    chat_store.set_user_approval_status(employee_id, chat_store.APPROVAL_APPROVED)
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


def test_qa_response_shape_stable_for_frontend(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4014")

    monkeypatch.setattr(
        "backend.app.api.routers.rag.ask_question",
        lambda **kwargs: {
            "answer": "Stable envelope answer.",
            "sources": [
                {
                    "content": "Clause excerpt",
                    "metadata": {"source": "digital_lending_2025.pdf", "page": 5},
                }
            ],
        },
    )

    response = client.post(
        "/api/v1/chat/ask",
        headers=headers,
        json={"question": "Explain borrower consent", "model_id": "phi:2.7b", "top_k": 4},
    )

    assert response.status_code == 200
    body = response.json()
    data = body["data"]

    assert set(["mode", "answer", "sources", "formatted_sources", "metadata"]).issubset(data.keys())
    assert data["mode"] == "qa"
    assert isinstance(data["sources"], list)
    assert isinstance(data["formatted_sources"], list)
    assert isinstance(data["metadata"], dict)
    assert "top_k" in data["metadata"]
    assert "elapsed_ms" in data["metadata"]


def test_qa_endpoint_includes_circular_linking_payload_shape(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4015")

    monkeypatch.setattr(
        "backend.app.api.routers.rag.ask_question",
        lambda **kwargs: {
            "answer": "Linking aware answer",
            "sources": [
                {
                    "content": "Primary source snippet",
                    "metadata": {"source": "digital_lending_2025.pdf.pdf", "page": 4},
                }
            ],
            "circular_linking": {
                "related_circulars": [
                    {
                        "relation_type": "amends",
                        "source": "digital_lending_2022.pdf.pdf",
                        "document_title": "Guidelines on Digital Lending",
                        "confidence": 0.93,
                        "rationale": "amends field references the older circular",
                    }
                ],
                "related_clauses": [
                    {
                        "relation_type": "amends",
                        "source": "digital_lending_2022.pdf.pdf",
                        "document_title": "Guidelines on Digital Lending",
                        "snippet": "Cooling-off period clause excerpt",
                        "confidence": 0.93,
                        "rationale": "same circular family",
                    }
                ],
            },
        },
    )

    response = client.post(
        "/api/v1/chat/ask",
        headers=headers,
        json={"question": "Link related circulars", "model_id": "phi:2.7b", "top_k": 4},
    )

    assert response.status_code == 200
    body = response.json()
    data = body["data"]

    assert data["mode"] == "qa"
    assert "sources" in data
    assert "formatted_sources" in data
    assert "circular_linking" in data

    linking = data["circular_linking"]
    assert isinstance(linking["related_circulars"], list)
    assert isinstance(linking["related_clauses"], list)
    assert linking["related_circulars"][0]["confidence"] == 0.93
    assert linking["related_circulars"][0]["rationale"]


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


def test_intent_triage_classifies_all_three_classes():
    assert triage_query_intent("What are the current KYC requirements?") == "fact_retrieval"
    assert triage_query_intent("How has digital lending changed since 2022?") == "timeline_analysis"
    assert triage_query_intent("Draft a KYC policy for our NBFC") == "drafting_request"


def test_temporal_endpoint_comparison_path(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4005")

    monkeypatch.setattr("backend.app.api.routers.rag.triage_query_intent", lambda question: "timeline_analysis")
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
    assert body["data"]["temporal"]["intent_class"] == "timeline_analysis"
    assert body["data"]["metadata"]["intent_class"] == "timeline_analysis"


def test_temporal_endpoint_returns_circular_linking_structure(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4016")

    monkeypatch.setattr("backend.app.api.routers.rag.triage_query_intent", lambda question: "timeline_analysis")
    monkeypatch.setattr(
        "backend.app.api.routers.rag.ask_temporal_question",
        lambda **kwargs: {
            "fallback": False,
            "single_version": False,
            "comparison": {
                "difflib_result": "- old\n+ new",
                "llm_summary": "Timeline summary",
            },
            "current_date": "2025-01-01",
            "previous_date": "2022-01-01",
            "document_title": "Guidelines on Digital Lending",
            "circular_linking": {
                "related_circulars": [
                    {
                        "relation_type": "parent_child",
                        "source": "DLG.pdf",
                        "document_title": "Digital Lending Guidelines - Detailed Reference",
                        "confidence": 0.81,
                        "rationale": "title overlap indicates hierarchy",
                    }
                ],
                "related_clauses": [
                    {
                        "relation_type": "parent_child",
                        "source": "DLG.pdf",
                        "document_title": "Digital Lending Guidelines - Detailed Reference",
                        "snippet": "Child circular clause",
                        "confidence": 0.81,
                        "rationale": "hierarchical relation",
                    }
                ],
            },
        },
    )

    response = client.post(
        "/api/v1/chat/ask-temporal",
        headers=headers,
        json={
            "question": "Show linked circulars for latest digital lending update",
            "model_id": "phi:2.7b",
            "top_k": 4,
            "comparison_method": "both",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "temporal_comparison"
    assert "circular_linking" in data
    assert data["circular_linking"]["related_circulars"][0]["confidence"] == 0.81
    assert data["circular_linking"]["related_circulars"][0]["rationale"]


def test_temporal_endpoint_fallback_and_single_version_paths(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4006")

    monkeypatch.setattr("backend.app.api.routers.rag.triage_query_intent", lambda question: "timeline_analysis")

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
    assert fallback_resp.json()["data"]["temporal"]["intent_class"] == "timeline_analysis"

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

    monkeypatch.setattr("backend.app.api.routers.rag.triage_query_intent", lambda question: "fact_retrieval")
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
    assert body["data"]["temporal"]["intent_class"] == "fact_retrieval"


def test_temporal_fast_mode_uses_direct_llm_path(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4017")

    monkeypatch.setattr("backend.app.api.routers.rag.triage_query_intent", lambda question: "fact_retrieval")
    monkeypatch.setattr(
        "backend.app.api.routers.rag.ask_direct_question",
        lambda **kwargs: {"answer": "Fast mode direct answer", "sources": []},
    )
    monkeypatch.setattr(
        "backend.app.api.routers.rag.ask_question",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("RAG path should not run for direct fast mode")),
    )

    response = client.post(
        "/api/v1/chat/ask-temporal",
        headers=headers,
        json={
            "question": "What is repo rate?",
            "model_id": "phi:2.7b",
            "top_k": 4,
            "comparison_method": "both",
            "mode": "fast",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["mode"] == "fast_direct"
    assert body["data"]["answer"] == "Fast mode direct answer"
    assert body["data"]["sources"] == []
    assert body["data"]["formatted_sources"] == []
    assert body["data"]["metadata"]["requested_mode"] == "fast"
    assert body["data"]["metadata"]["executed_mode"] == "fast"
    assert body["data"]["metadata"]["routing_reason"] == "fast_direct_path"


def test_temporal_fast_mode_auto_escalates_to_thinking(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4018")

    monkeypatch.setattr("backend.app.api.routers.rag.triage_query_intent", lambda question: "fact_retrieval")
    monkeypatch.setattr(
        "backend.app.api.routers.rag.ask_direct_question",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("Fast direct path should be skipped")),
    )
    monkeypatch.setattr(
        "backend.app.api.routers.rag.ask_question",
        lambda **kwargs: {"answer": "Grounded answer", "sources": []},
    )

    response = client.post(
        "/api/v1/chat/ask-temporal",
        headers=headers,
        json={
            "question": "Provide source and section references for KYC rules",
            "model_id": "phi:2.7b",
            "top_k": 4,
            "comparison_method": "both",
            "mode": "fast",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["mode"] == "qa_fallback_non_temporal"
    assert body["data"]["answer"] == "Grounded answer"
    assert body["data"]["metadata"]["requested_mode"] == "fast"
    assert body["data"]["metadata"]["executed_mode"] == "thinking"
    assert body["data"]["metadata"]["routing_reason"] == "citation_or_clause_request"


def test_temporal_mode_omitted_defaults_to_thinking(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4019")

    monkeypatch.setattr("backend.app.api.routers.rag.triage_query_intent", lambda question: "fact_retrieval")
    monkeypatch.setattr(
        "backend.app.api.routers.rag.ask_question",
        lambda **kwargs: {"answer": "Default thinking answer", "sources": []},
    )

    response = client.post(
        "/api/v1/chat/ask-temporal",
        headers=headers,
        json={
            "question": "What is KYC?",
            "model_id": "phi:2.7b",
            "top_k": 4,
            "comparison_method": "both",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["mode"] == "qa_fallback_non_temporal"
    assert body["data"]["metadata"]["requested_mode"] == "thinking"
    assert body["data"]["metadata"]["executed_mode"] == "thinking"
    assert body["data"]["metadata"]["routing_reason"] == "default_thinking_mode"


def test_temporal_drafting_query_routes_to_stub(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4009")

    monkeypatch.setattr("backend.app.api.routers.rag.triage_query_intent", lambda question: "drafting_request")

    response = client.post(
        "/api/v1/chat/ask-temporal",
        headers=headers,
        json={
            "question": "Draft a KYC policy for our lending business",
            "model_id": "phi:2.7b",
            "top_k": 4,
            "comparison_method": "both",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["mode"] == "drafting_stub"
    assert body["data"]["temporal"]["intent_class"] == "drafting_request"
    assert body["data"]["temporal"]["fallback_reason"] == "drafting_request_stub"
    assert body["data"]["sources"] == []
    assert body["data"]["formatted_sources"] == []
    assert "Drafting request detected" in body["data"]["answer"]


def test_temporal_timeout_error_mapping(client: TestClient, monkeypatch):
    headers = _auth_headers(client, employee_id="EMP4008")

    monkeypatch.setattr("backend.app.api.routers.rag.triage_query_intent", lambda question: "timeline_analysis")
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


def test_hybrid_ranking_prefers_keyword_signal(monkeypatch):
    import query as query_module

    class FakeDocStore:
        def __init__(self, docs: dict[str, Document]):
            self.docs = docs

        def search(self, doc_id: str):
            return self.docs.get(doc_id)

    class FakeVectorStore:
        def __init__(self, scored_docs: list[tuple[Document, float]]):
            self.scored_docs = scored_docs
            self.index_to_docstore_id = {
                idx: f"doc-{idx}" for idx, _ in enumerate(scored_docs)
            }
            self.docstore = FakeDocStore(
                {f"doc-{idx}": doc for idx, (doc, _) in enumerate(scored_docs)}
            )

        def similarity_search_with_score(self, question: str, k: int):
            return self.scored_docs[:k]

        def similarity_search(self, question: str, k: int):
            return [doc for doc, _ in self.scored_docs[:k]]

    vector_favored_doc = Document(
        page_content="Reserve ratio and branch authorization framework.",
        metadata={"source": "vector_doc.pdf", "page": 1, "document_title": "Reserve Policy"},
    )
    keyword_favored_doc = Document(
        page_content="Digital lending borrower consent requirements and grievance timelines.",
        metadata={"source": "keyword_doc.pdf", "page": 2, "document_title": "Digital Lending Consent"},
    )

    fake_store = FakeVectorStore(
        [
            (vector_favored_doc, 0.01),
            (keyword_favored_doc, 1.20),
        ]
    )

    class DummyLLM:
        def invoke(self, final_prompt: str) -> str:
            return "Hybrid answer"

    monkeypatch.setattr(query_module, "load_vectorstore", lambda: fake_store)
    monkeypatch.setattr(query_module, "get_llm", lambda model_name="": DummyLLM())
    monkeypatch.setattr(
        query_module,
        "get_hybrid_retrieval_settings",
        lambda: {
            "vector_weight": 0.2,
            "keyword_weight": 0.8,
            "candidate_multiplier": 4,
            "keyword_min_token_length": 3,
        },
    )

    result = query_module.ask_question(
        question="What are borrower consent requirements in digital lending?",
        k=1,
        model_name="phi:2.7b",
    )

    assert result["answer"] == "Hybrid answer"
    assert len(result["sources"]) == 1
    assert result["sources"][0]["metadata"]["source"] == "keyword_doc.pdf"


def test_circular_linking_resolver_handles_amendment_and_parent_child_relations():
    class FakeDocStore:
        def __init__(self, docs: dict[str, Document]):
            self.docs = docs

        def search(self, doc_id: str):
            return self.docs.get(doc_id)

    class FakeVectorStore:
        def __init__(self, docs: list[Document]):
            self.index_to_docstore_id = {idx: f"doc-{idx}" for idx in range(len(docs))}
            self.docstore = FakeDocStore({f"doc-{idx}": doc for idx, doc in enumerate(docs)})

    parent_doc = Document(
        page_content="Parent circular clause about baseline KYC obligations.",
        metadata={
            "source": "parent_circular.pdf",
            "document_title": "Master Direction on KYC",
            "regulator": "RBI",
            "version_date": "2022-01-01",
            "effective_date": "2022-01-01",
            "amends": None,
        },
    )
    child_doc = Document(
        page_content="Child circular clause adding NBFC-specific controls.",
        metadata={
            "source": "parent_circular_nbfc_addendum.pdf",
            "document_title": "Master Direction on KYC - NBFC Addendum",
            "regulator": "RBI",
            "version_date": "2024-01-01",
            "effective_date": "2024-01-01",
            "amends": "parent_circular.pdf",
        },
    )

    fake_store = FakeVectorStore([parent_doc, child_doc])
    linking = resolve_circular_links(fake_store, [child_doc], max_related=6)

    assert isinstance(linking["related_circulars"], list)
    assert isinstance(linking["related_clauses"], list)
    assert linking["related_circulars"]
    assert linking["related_clauses"]

    relation_types = {entry["relation_type"] for entry in linking["related_circulars"]}
    assert "amends" in relation_types
    assert "parent_child" in relation_types

    for entry in linking["related_circulars"]:
        assert "confidence" in entry
        assert isinstance(entry["confidence"], float)
        assert "rationale" in entry
        assert entry["rationale"]

    for entry in linking["related_clauses"]:
        assert "confidence" in entry
        assert isinstance(entry["confidence"], float)
        assert "rationale" in entry
        assert entry["rationale"]
