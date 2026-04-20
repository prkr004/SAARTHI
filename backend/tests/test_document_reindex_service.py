"""Regression coverage for registry-driven no-downtime reindex behavior."""

from __future__ import annotations

import copy
import pickle
from pathlib import Path
from types import SimpleNamespace

import chat_store
import pytest
from langchain_core.documents import Document

from backend.app.services import document_reindex_service


class DummyEmbeddings:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or "dummy"

    def embed_documents(self, texts):
        return [[0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [0.0, 0.0, 0.0]


class _DummyDocstore:
    def __init__(self, mapping: dict[str, Document]):
        self._mapping = mapping

    def search(self, doc_id: str):
        return self._mapping.get(doc_id)


class DummyFAISS:
    def __init__(self, docs: list[Document] | None = None):
        self.docs = [copy.deepcopy(doc) for doc in (docs or [])]
        self._refresh_docstore()

    def _refresh_docstore(self) -> None:
        mapping: dict[str, Document] = {}
        self.index_to_docstore_id: dict[int, str] = {}
        for index, doc in enumerate(self.docs):
            doc_id = f"doc-{index}"
            self.index_to_docstore_id[index] = doc_id
            mapping[doc_id] = copy.deepcopy(doc)
        self.docstore = _DummyDocstore(mapping)

    @classmethod
    def from_documents(cls, docs: list[Document], embeddings: DummyEmbeddings):
        return cls(docs)

    @classmethod
    def load_local(cls, index_path: str, embeddings: DummyEmbeddings, allow_dangerous_deserialization: bool = True):
        docs_file = Path(index_path) / "docs.pkl"
        if not docs_file.exists():
            raise FileNotFoundError(f"Fake index not found at {index_path}")
        docs = pickle.loads(docs_file.read_bytes())
        return cls(docs)

    def add_documents(self, docs: list[Document]) -> None:
        self.docs.extend(copy.deepcopy(docs))
        self._refresh_docstore()

    def save_local(self, index_path: str) -> None:
        path = Path(index_path)
        path.mkdir(parents=True, exist_ok=True)
        (path / "index.faiss").write_bytes(b"fake-faiss")
        (path / "index.pkl").write_bytes(b"fake-pickle")
        (path / "docs.pkl").write_bytes(pickle.dumps(self.docs))


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_store, "DB_PATH", tmp_path / "saarthi_secure_test.db")
    chat_store.initialize_db()
    bootstrap = chat_store.bootstrap_admin_user()
    assert bootstrap.success
    return tmp_path


@pytest.fixture(autouse=True)
def patch_reindex_runtime(monkeypatch, tmp_path):
    index_directory = tmp_path / "faiss_index"
    settings = SimpleNamespace(faiss_index_path=str(index_directory / "index.faiss"))

    monkeypatch.setattr(document_reindex_service, "get_settings", lambda: settings)
    monkeypatch.setattr(document_reindex_service, "HuggingFaceEmbeddings", DummyEmbeddings)
    monkeypatch.setattr(document_reindex_service, "FAISS", DummyFAISS)

    return index_directory


def test_registry_reindex_applies_soft_delete_and_metadata_updates(isolated_db, patch_reindex_runtime, monkeypatch):
    index_directory = patch_reindex_runtime

    active_row = chat_store.upsert_document_registry_entry(
        document_key="active_source.pdf|active policy|2026-04-20",
        source="active_source.pdf",
        document_title="Active Policy",
        version_date="2026-04-20",
        effective_date="2026-04-20",
        regulator="RBI",
        document_status="Active",
        chunk_count=2,
    )
    assert chat_store.update_document_registry_metadata(
        int(active_row["id"]),
        regulator="Reserve Bank of India",
        document_status="Current",
    )

    deleted_row = chat_store.upsert_document_registry_entry(
        document_key="deleted_source.pdf|deleted policy|2026-04-20",
        source="deleted_source.pdf",
        document_title="Deleted Policy",
        version_date="2026-04-20",
        effective_date="2026-04-20",
        regulator="RBI",
        document_status="Active",
        chunk_count=1,
    )
    assert chat_store.soft_delete_document(int(deleted_row["id"]), deleted_reason="Superseded")

    source_docs = [
        Document(
            page_content="active chunk",
            metadata={
                "source": "active_source.pdf",
                "document_title": "Active Policy",
                "version_date": "2026-04-20",
                "effective_date": "2026-04-20",
                "regulator": "RBI",
                "status": "Active",
                "page": 1,
            },
        ),
        Document(
            page_content="deleted chunk",
            metadata={
                "source": "deleted_source.pdf",
                "document_title": "Deleted Policy",
                "version_date": "2026-04-20",
                "effective_date": "2026-04-20",
                "regulator": "RBI",
                "status": "Active",
                "page": 1,
            },
        ),
        Document(
            page_content="orphan chunk",
            metadata={
                "source": "orphan_source.pdf",
                "document_title": "Orphan Policy",
                "version_date": "2026-04-20",
                "page": 1,
            },
        ),
    ]
    DummyFAISS.from_documents(source_docs, DummyEmbeddings("dummy")).save_local(str(index_directory))

    cache_refresh_calls = {"count": 0}

    def fake_refresh_rag_caches():
        cache_refresh_calls["count"] += 1

    monkeypatch.setattr(document_reindex_service, "refresh_rag_caches", fake_refresh_rag_caches)

    outcome = document_reindex_service.run_registry_reindex(
        trigger="unit_test",
        document_id=int(active_row["id"]),
        actor_user_id=1,
    )

    assert outcome["success"] is True
    assert outcome["reason"] == "reindexed"
    assert int(outcome["dropped_chunks"]) == 1
    assert int(outcome["metadata_updates"]) >= 1
    assert cache_refresh_calls["count"] == 1

    reloaded = DummyFAISS.load_local(str(index_directory), DummyEmbeddings("dummy"))
    sources = {str(doc.metadata.get("source")) for doc in reloaded.docs}
    assert "deleted_source.pdf" not in sources
    assert "active_source.pdf" in sources
    assert "orphan_source.pdf" in sources

    active_doc = next(doc for doc in reloaded.docs if doc.metadata.get("source") == "active_source.pdf")
    assert active_doc.metadata.get("regulator") == "Reserve Bank of India"
    assert active_doc.metadata.get("status") == "Current"
    assert active_doc.metadata.get("document_status") == "Current"

    previous_dir = index_directory.parent / f"{index_directory.name}__previous"
    assert previous_dir.exists()


def test_registry_reindex_skips_when_no_registry_delta(isolated_db, patch_reindex_runtime, monkeypatch):
    index_directory = patch_reindex_runtime

    source_docs = [
        Document(
            page_content="independent chunk",
            metadata={
                "source": "independent_source.pdf",
                "document_title": "Independent Policy",
                "version_date": "2026-04-20",
                "page": 1,
            },
        )
    ]
    DummyFAISS.from_documents(source_docs, DummyEmbeddings("dummy")).save_local(str(index_directory))

    cache_refresh_calls = {"count": 0}

    def fake_refresh_rag_caches():
        cache_refresh_calls["count"] += 1

    monkeypatch.setattr(document_reindex_service, "refresh_rag_caches", fake_refresh_rag_caches)

    outcome = document_reindex_service.run_registry_reindex(trigger="unit_test_noop")

    assert outcome["success"] is True
    assert outcome["reason"] == "no_registry_delta"
    assert int(outcome["matched_chunks"]) == 0
    assert int(outcome["dropped_chunks"]) == 0
    assert int(outcome["metadata_updates"]) == 0
    assert cache_refresh_calls["count"] == 0


def test_atomic_swap_rolls_back_on_swap_failure(tmp_path, monkeypatch):
    current_dir = tmp_path / "index_current"
    rebuilt_dir = tmp_path / "index_rebuilt"
    current_dir.mkdir(parents=True, exist_ok=True)
    rebuilt_dir.mkdir(parents=True, exist_ok=True)

    (current_dir / "marker.txt").write_text("current", encoding="utf-8")
    (rebuilt_dir / "marker.txt").write_text("rebuilt", encoding="utf-8")

    original_rename = Path.rename
    calls = {"count": 0}

    def flaky_rename(self: Path, target):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated swap failure")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky_rename)

    with pytest.raises(OSError, match="simulated swap failure"):
        document_reindex_service._atomic_swap_index_directories(current_dir, rebuilt_dir)

    assert current_dir.exists()
    assert (current_dir / "marker.txt").read_text(encoding="utf-8") == "current"
