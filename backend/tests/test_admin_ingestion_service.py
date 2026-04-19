"""Regression coverage for admin ingestion into the shared RAG index."""

from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import chat_store
import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document

import query
from backend.app.main import app
from backend.app.services import admin_ingestion_service


class DummyEmbeddings:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or "dummy"

    def embed_documents(self, texts):
        return [[0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [0.0, 0.0, 0.0]


class DummyLLM:
    def invoke(self, prompt: str) -> str:
        return "Stub answer from fake model."


class FakeFAISS:
    persisted_docs: dict[str, list[Document]] = {}

    def __init__(self, docs: list[Document] | None = None):
        self.docs = list(docs or [])

    @classmethod
    def clear(cls) -> None:
        cls.persisted_docs.clear()

    @classmethod
    def from_documents(cls, docs: list[Document], embeddings: DummyEmbeddings):
        return cls([copy.deepcopy(doc) for doc in docs])

    @classmethod
    def load_local(cls, index_path: str, embeddings: DummyEmbeddings, allow_dangerous_deserialization: bool = True):
        key = str(Path(index_path).resolve())
        if key not in cls.persisted_docs:
            raise FileNotFoundError(f"Fake index not found at {index_path}")
        return cls([copy.deepcopy(doc) for doc in cls.persisted_docs[key]])

    def add_documents(self, docs: list[Document]) -> None:
        self.docs.extend(copy.deepcopy(list(docs)))

    def save_local(self, index_path: str) -> None:
        key = str(Path(index_path).resolve())
        path = Path(index_path)
        path.mkdir(parents=True, exist_ok=True)
        (path / "index.faiss").write_bytes(b"fake-faiss")
        (path / "index.pkl").write_bytes(b"fake-pickle")
        self.__class__.persisted_docs[key] = [copy.deepcopy(doc) for doc in self.docs]

    def similarity_search_with_score(self, question: str, k: int):
        docs = self.docs[:k]
        return [(doc, float(index)) for index, doc in enumerate(docs)]

    def similarity_search(self, question: str, k: int):
        return self.docs[:k]


def _auth_headers(client: TestClient, employee_id: str) -> dict[str, str]:
    password = "SecurePass#123"
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "employee_id": employee_id,
            "full_name": "Ingestion Regression User",
            "password": password,
            "email": f"{employee_id.lower()}@example.com",
        },
    )
    assert register_response.status_code == 201

    assert chat_store.set_user_approval_status(employee_id, chat_store.APPROVAL_APPROVED)

    login_response = client.post(
        "/api/v1/auth/login",
        json={"employee_id": employee_id, "password": password},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_admin_job(*, total_files: int) -> dict:
    admin = chat_store.get_user_by_employee_id(chat_store.DEFAULT_ADMIN_EMPLOYEE_ID)
    assert admin is not None
    return chat_store.create_ingestion_job(created_by=int(admin["id"]), total_files=total_files)


def _patch_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    index_directory = tmp_path / "faiss_index"
    settings = SimpleNamespace(
        faiss_index_path=str(index_directory / "index.faiss"),
        admin_upload_directory=str(tmp_path / "admin_uploads"),
        admin_upload_max_files_per_job=12,
        admin_upload_max_file_size_mb=20,
    )

    monkeypatch.setattr(admin_ingestion_service, "get_settings", lambda: settings)
    monkeypatch.setattr(admin_ingestion_service, "HuggingFaceEmbeddings", DummyEmbeddings)
    monkeypatch.setattr(admin_ingestion_service, "FAISS", FakeFAISS)

    monkeypatch.setattr(query, "_default_index_path", lambda: str(index_directory))
    monkeypatch.setattr(query, "FAISS", FakeFAISS)

    @lru_cache(maxsize=1)
    def fake_get_embeddings():
        return DummyEmbeddings("dummy")

    @lru_cache(maxsize=4)
    def fake_get_llm(model_name: str = query.DEFAULT_OLLAMA_MODEL):
        return DummyLLM()

    monkeypatch.setattr(query, "get_embeddings", fake_get_embeddings)
    monkeypatch.setattr(query, "get_llm", fake_get_llm)
    monkeypatch.setattr(
        query,
        "_resolve_circular_linking_payload",
        lambda vectorstore, focus_docs: {"related_circulars": [], "related_clauses": []},
    )

    return index_directory


def _fake_chunk_loader(pdf_path: str, **kwargs):
    source_path = str(Path(pdf_path).resolve())
    return [
        Document(
            page_content=f"{Path(pdf_path).stem} compliance obligations and controls",
            metadata={
                "source": source_path,
                "page": 1,
                "regulator": kwargs.get("regulator"),
                "document_title": kwargs.get("document_title"),
                "version_date": kwargs.get("version_date"),
                "effective_date": kwargs.get("effective_date"),
                "status": kwargs.get("status"),
                "amends": kwargs.get("amends"),
            },
        )
    ]


@pytest.fixture(autouse=True)
def _reset_state():
    FakeFAISS.clear()

    if hasattr(query.load_vectorstore, "cache_clear"):
        query.load_vectorstore.cache_clear()
    if hasattr(query.get_embeddings, "cache_clear"):
        query.get_embeddings.cache_clear()
    if hasattr(query.get_llm, "cache_clear"):
        query.get_llm.cache_clear()
    if hasattr(query.get_hybrid_retrieval_settings, "cache_clear"):
        query.get_hybrid_retrieval_settings.cache_clear()

    yield

    FakeFAISS.clear()
    if hasattr(query.load_vectorstore, "cache_clear"):
        query.load_vectorstore.cache_clear()
    if hasattr(query.get_embeddings, "cache_clear"):
        query.get_embeddings.cache_clear()
    if hasattr(query.get_llm, "cache_clear"):
        query.get_llm.cache_clear()
    if hasattr(query.get_hybrid_retrieval_settings, "cache_clear"):
        query.get_hybrid_retrieval_settings.cache_clear()


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(chat_store, "DB_PATH", tmp_path / "saarthi_secure_test.db")
    chat_store.initialize_db()
    bootstrap = chat_store.bootstrap_admin_user()
    assert bootstrap.success
    return tmp_path


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chat_store, "DB_PATH", tmp_path / "saarthi_secure_test.db")
    with TestClient(app) as test_client:
        yield test_client


def test_single_file_ingestion_adds_chunks_when_index_already_exists(isolated_db: Path, monkeypatch: pytest.MonkeyPatch):
    index_directory = _patch_runtime(monkeypatch, isolated_db)
    monkeypatch.setattr(admin_ingestion_service, "load_and_chunk_pdf", _fake_chunk_loader)

    baseline = Document(page_content="baseline context", metadata={"source": "baseline.pdf", "page": 1})
    FakeFAISS.from_documents([baseline], DummyEmbeddings("dummy")).save_local(str(index_directory))

    uploaded_file = isolated_db / "uploaded_single.pdf"
    uploaded_file.write_bytes(b"%PDF-1.4\n")

    job = _create_admin_job(total_files=1)
    admin_ingestion_service.start_ingestion_job(job_id=str(job["job_id"]), stored_files=[uploaded_file])

    updated = chat_store.get_ingestion_job(str(job["job_id"]))
    assert updated is not None
    assert updated["status"] == chat_store.INGESTION_STATUS_COMPLETED
    assert updated["processed_files"] == 1
    assert updated["total_chunks"] == 1

    persisted = FakeFAISS.persisted_docs[str(index_directory.resolve())]
    assert len(persisted) == 2

    uploaded_source = str(uploaded_file.resolve())
    uploaded_doc = next(doc for doc in persisted if doc.metadata.get("source") == uploaded_source)
    assert uploaded_doc.metadata.get("page") == 1
    assert uploaded_doc.metadata.get("regulator") == "Admin Upload"
    assert uploaded_doc.metadata.get("document_title")
    assert uploaded_doc.metadata.get("version_date")
    assert uploaded_doc.metadata.get("effective_date")


def test_multi_file_ingestion_indexes_all_files(isolated_db: Path, monkeypatch: pytest.MonkeyPatch):
    index_directory = _patch_runtime(monkeypatch, isolated_db)
    monkeypatch.setattr(admin_ingestion_service, "load_and_chunk_pdf", _fake_chunk_loader)

    baseline = Document(page_content="baseline context", metadata={"source": "baseline.pdf", "page": 1})
    FakeFAISS.from_documents([baseline], DummyEmbeddings("dummy")).save_local(str(index_directory))

    first_file = isolated_db / "first_upload.pdf"
    second_file = isolated_db / "second_upload.pdf"
    first_file.write_bytes(b"%PDF-1.4\n")
    second_file.write_bytes(b"%PDF-1.4\n")

    job = _create_admin_job(total_files=2)
    admin_ingestion_service.start_ingestion_job(
        job_id=str(job["job_id"]),
        stored_files=[first_file, second_file],
    )

    updated = chat_store.get_ingestion_job(str(job["job_id"]))
    assert updated is not None
    assert updated["status"] == chat_store.INGESTION_STATUS_COMPLETED
    assert updated["processed_files"] == 2
    assert updated["total_chunks"] == 2

    persisted = FakeFAISS.persisted_docs[str(index_directory.resolve())]
    sources = {str(doc.metadata.get("source")) for doc in persisted}
    assert str(first_file.resolve()) in sources
    assert str(second_file.resolve()) in sources


def test_uploaded_doc_is_queryable_in_chat_without_restart(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    index_directory = _patch_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(admin_ingestion_service, "load_and_chunk_pdf", _fake_chunk_loader)

    baseline = Document(page_content="baseline context only", metadata={"source": "baseline.pdf", "page": 1})
    FakeFAISS.from_documents([baseline], DummyEmbeddings("dummy")).save_local(str(index_directory))

    # Warm the query cache before ingestion so cache refresh is required for new data visibility.
    query.load_vectorstore()

    uploaded_file = tmp_path / "payment_regulatory.pdf"
    uploaded_file.write_bytes(b"%PDF-1.4\n")

    job = _create_admin_job(total_files=1)
    admin_ingestion_service.start_ingestion_job(job_id=str(job["job_id"]), stored_files=[uploaded_file])

    updated = chat_store.get_ingestion_job(str(job["job_id"]))
    assert updated is not None
    assert updated["status"] == chat_store.INGESTION_STATUS_COMPLETED
    assert updated["total_chunks"] == 1

    headers = _auth_headers(client, employee_id="EMP7701")
    response = client.post(
        "/api/v1/chat/ask",
        headers=headers,
        json={"question": "What does payment regulatory require?", "top_k": 4},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    data = payload["data"]
    uploaded_source = str(uploaded_file.resolve())
    assert any(src.get("metadata", {}).get("source") == uploaded_source for src in data["sources"])
    assert any("payment_regulatory" in (src.get("document_name") or "").lower() for src in data["formatted_sources"])
    assert data["answer"] == "Stub answer from fake model."
