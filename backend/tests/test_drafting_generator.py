"""Drafting generator fallback behavior tests."""

from __future__ import annotations

from langchain_core.documents import Document

import backend.app.drafting.generator as drafting_generator
from backend.app.drafting.schema import AdvisoryDraft, CircularDraft


def _stub_retrieval(monkeypatch, docs: list[Document]) -> None:
    monkeypatch.setattr(drafting_generator, "load_vectorstore", lambda: object())
    monkeypatch.setattr(
        drafting_generator,
        "retrieve_relevant_docs",
        lambda vectorstore, question, k: docs,
    )
    monkeypatch.setattr(drafting_generator, "detect_temporal_intent", lambda _: False)


def test_generate_document_falls_back_when_model_unavailable(monkeypatch):
    docs = [
        Document(
            page_content=(
                "Regulated entities must strengthen KYC checks and enhance customer due-diligence "
                "for high-risk accounts."
            ),
            metadata={"source": "masterdirectionkyc.pdf", "page": 12},
        )
    ]
    _stub_retrieval(monkeypatch, docs)

    class BrokenLLM:
        def invoke(self, _: str):
            raise RuntimeError(
                "HTTPConnectionPool(host='localhost', port=11434): Max retries exceeded "
                "with url: /api/generate"
            )

    monkeypatch.setattr(drafting_generator, "get_llm", lambda model_name="": BrokenLLM())

    result = drafting_generator.generate_document(
        document_type="circular",
        user_input={"query": "KYC update 2025", "audience": "internal"},
    )

    assert isinstance(result, CircularDraft)
    assert result.document_type == "circular"
    assert result.reference_number.startswith("HO Circular No.")
    assert result.subject.lower().startswith("operational circular on")
    assert len(result.highlights) >= 1
    assert len(result.operational_directives) >= 1
    assert "model fallback reason" in result.compliance_warning.lower()


def test_generate_document_falls_back_on_invalid_model_payload(monkeypatch):
    docs = [
        Document(
            page_content="Digital lending disclosures must include transparent borrower obligations.",
            metadata={"source": "digital_lending_2025.pdf", "page": 4},
        )
    ]
    _stub_retrieval(monkeypatch, docs)

    class InvalidPayloadLLM:
        def invoke(self, _: str) -> str:
            return "This is not valid JSON"

    monkeypatch.setattr(drafting_generator, "get_llm", lambda model_name="": InvalidPayloadLLM())

    result = drafting_generator.generate_document(
        document_type="advisory",
        user_input={"query": "Borrower disclosure update", "audience": "operations"},
    )

    assert isinstance(result, AdvisoryDraft)
    assert result.document_type == "advisory"
    assert result.priority_level == "URGENT"
    assert len(result.mitigating_actions) >= 1
    assert "central compliance cell" in result.reporting_mechanism.lower()