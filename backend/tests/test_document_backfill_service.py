"""Backfill service regression tests for grouping, enrichment, and idempotency."""

from __future__ import annotations

from langchain_core.documents import Document
import chat_store
import pytest

from backend.app.services import document_backfill_service


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_store, "DB_PATH", tmp_path / "saarthi_secure_test.db")
    chat_store.initialize_db()
    bootstrap = chat_store.bootstrap_admin_user()
    assert bootstrap.success
    return tmp_path


def test_grouping_uses_source_title_version_tuple():
    chunks = [
        Document(
            page_content="A chunk one",
            metadata={
                "source": "a.pdf",
                "document_title": "Digital Lending Guidelines",
                "version_date": "2024-01-01",
                "effective_date": "2024-01-01",
                "regulator": "RBI",
                "status": "Active",
                "page": 1,
            },
        ),
        Document(
            page_content="A chunk two",
            metadata={
                "source": "a.pdf",
                "document_title": "Digital Lending Guidelines",
                "version_date": "2024-01-01",
                "effective_date": "2024-01-01",
                "regulator": "RBI",
                "status": "Active",
                "page": 2,
            },
        ),
        Document(
            page_content="A variant source",
            metadata={
                "source": "b.pdf",
                "document_title": "Digital Lending Guidelines",
                "version_date": "2024-01-01",
                "effective_date": "2024-01-01",
                "regulator": "RBI",
                "status": "Active",
                "page": 3,
            },
        ),
        Document(
            page_content="A newer version",
            metadata={
                "source": "a.pdf",
                "document_title": "Digital Lending Guidelines",
                "version_date": "2025-01-01",
                "effective_date": "2025-01-01",
                "regulator": "RBI",
                "status": "Active",
                "page": 1,
            },
        ),
    ]

    grouped = document_backfill_service.group_indexed_documents(chunks)
    assert len(grouped) == 3

    by_key = {item["document_key"]: item for item in grouped}

    key_old_a = "a.pdf|digital lending guidelines|2024-01-01"
    key_old_b = "b.pdf|digital lending guidelines|2024-01-01"
    key_new_a = "a.pdf|digital lending guidelines|2025-01-01"

    assert by_key[key_old_a]["chunk_count"] == 2
    assert by_key[key_old_a]["metadata"]["page_min"] == 1
    assert by_key[key_old_a]["metadata"]["page_max"] == 2

    assert by_key[key_old_b]["chunk_count"] == 1
    assert by_key[key_new_a]["chunk_count"] == 1


def test_grouping_handles_missing_metadata_with_manifest_enrichment():
    manifest_entries = [
        {
            "pdf_path": "MasterDirectionKYC.pdf",
            "regulator": "RBI",
            "document_title": "Master Direction on KYC",
            "version_date": "2016-02-25",
            "effective_date": "2016-02-25",
            "status": "Active",
            "amends": None,
        }
    ]

    enriched_chunks = [
        Document(
            page_content="KYC excerpt",
            metadata={
                "source": "C:/docs/MasterDirectionKYC.pdf",
                "page": 8,
                "effective_date": "2016-02-25",
            },
        )
    ]

    enriched_grouped = document_backfill_service.group_indexed_documents(
        enriched_chunks,
        manifest_entries=manifest_entries,
    )

    assert len(enriched_grouped) == 1
    row = enriched_grouped[0]
    assert row["document_title"] == "Master Direction on KYC"
    assert row["version_date"] == "2016-02-25"
    assert row["effective_date"] == "2016-02-25"
    assert row["regulator"] == "RBI"
    assert row["document_status"] == "Active"
    assert row["metadata"]["manifest_enriched"] is True

    fallback_chunks = [
        Document(
            page_content="Fallback excerpt",
            metadata={
                "document_title": "Fallback Circular",
                "effective_date": "2024-03-31",
                "page": 1,
            },
        )
    ]

    fallback_grouped = document_backfill_service.group_indexed_documents(
        fallback_chunks,
        manifest_entries=[],
    )

    assert len(fallback_grouped) == 1
    fallback = fallback_grouped[0]
    assert fallback["source"].startswith("unknown_source|")
    assert fallback["version_date"] == "2024-03-31"
    assert fallback["document_title"] == "Fallback Circular"


def test_grouping_includes_manifest_only_entries_without_chunks():
    manifest_entries = [
        {
            "pdf_path": "rbi_doc.pdf",
            "regulator": "RBI",
            "document_title": "RBI Circular",
            "version_date": "2024-01-01",
            "effective_date": "2024-01-01",
            "status": "Active",
            "amends": None,
        },
        {
            "pdf_path": "sebi_doc.pdf",
            "regulator": "SEBI",
            "document_title": "SEBI Circular",
            "version_date": "2024-02-01",
            "effective_date": "2024-02-01",
            "status": "Active",
            "amends": None,
        },
    ]

    chunks = [
        Document(
            page_content="Indexed chunk",
            metadata={
                "source": "rbi_doc.pdf",
                "document_title": "RBI Circular",
                "version_date": "2024-01-01",
                "effective_date": "2024-01-01",
                "regulator": "RBI",
                "status": "Active",
                "page": 1,
            },
        )
    ]

    grouped = document_backfill_service.group_indexed_documents(
        chunks,
        manifest_entries=manifest_entries,
    )

    assert len(grouped) == 2
    by_key = {item["document_key"]: item for item in grouped}

    assert "rbi_doc.pdf|rbi circular|2024-01-01" in by_key
    assert "sebi_doc.pdf|sebi circular|2024-02-01" in by_key

    assert by_key["rbi_doc.pdf|rbi circular|2024-01-01"]["chunk_count"] == 1
    assert by_key["rbi_doc.pdf|rbi circular|2024-01-01"]["metadata"]["manifest_enriched"] is True

    assert by_key["sebi_doc.pdf|sebi circular|2024-02-01"]["chunk_count"] == 0
    assert by_key["sebi_doc.pdf|sebi circular|2024-02-01"]["metadata"]["backfill_origin"] == "manifest_only"


def test_backfill_pipeline_is_idempotent_and_updates_job_progress(isolated_db, monkeypatch):
    chunks = [
        Document(
            page_content="doc-a chunk one",
            metadata={
                "source": "a.pdf",
                "document_title": "Doc A",
                "version_date": "2024-01-01",
                "effective_date": "2024-01-01",
                "regulator": "RBI",
                "status": "Active",
                "page": 1,
            },
        ),
        Document(
            page_content="doc-a chunk two",
            metadata={
                "source": "a.pdf",
                "document_title": "Doc A",
                "version_date": "2024-01-01",
                "effective_date": "2024-01-01",
                "regulator": "RBI",
                "status": "Active",
                "page": 2,
            },
        ),
        Document(
            page_content="doc-b chunk one",
            metadata={
                "source": "b.pdf",
                "document_title": "Doc B",
                "version_date": "2024-02-01",
                "effective_date": "2024-02-01",
                "regulator": "RBI",
                "status": "Active",
                "page": 1,
            },
        ),
    ]

    monkeypatch.setattr(
        document_backfill_service,
        "_resolve_index_directory",
        lambda: isolated_db / "faiss_index",
    )
    monkeypatch.setattr(
        document_backfill_service,
        "_load_index_documents",
        lambda _index_directory: list(chunks),
    )
    monkeypatch.setattr(
        document_backfill_service,
        "_load_manifest_entries",
        lambda _manifest_path=None: [],
    )

    refresh_calls = {"count": 0}

    def fake_refresh_rag_caches():
        refresh_calls["count"] += 1

    monkeypatch.setattr(document_backfill_service, "refresh_rag_caches", fake_refresh_rag_caches)

    admin = chat_store.get_user_by_employee_id(chat_store.DEFAULT_ADMIN_EMPLOYEE_ID)
    assert admin is not None
    admin_id = int(admin["id"])

    first_job = chat_store.create_backfill_job(created_by=admin_id, total_documents=0)
    document_backfill_service.start_document_backfill_job(job_id=str(first_job["job_id"]))

    first_job_state = chat_store.get_backfill_job(str(first_job["job_id"]))
    assert first_job_state is not None
    assert first_job_state["status"] == chat_store.BACKFILL_STATUS_COMPLETED
    assert first_job_state["total_documents"] == 2
    assert first_job_state["processed_documents"] == 2
    assert first_job_state["discovered_chunks"] == 3
    assert first_job_state["progress_percent"] == 100
    assert first_job_state["completed_at"]

    after_first = {
        item["document_key"]: item
        for item in chat_store.list_documents(include_deleted=True, limit=100)
    }
    assert len(after_first) == 2
    assert after_first["a.pdf|doc a|2024-01-01"]["chunk_count"] == 2
    assert after_first["b.pdf|doc b|2024-02-01"]["chunk_count"] == 1
    assert after_first["a.pdf|doc a|2024-01-01"]["summary_status"] == chat_store.DOCUMENT_SUMMARY_STATUS_PENDING

    second_job = chat_store.create_backfill_job(created_by=admin_id, total_documents=0)
    document_backfill_service.start_document_backfill_job(job_id=str(second_job["job_id"]))

    second_job_state = chat_store.get_backfill_job(str(second_job["job_id"]))
    assert second_job_state is not None
    assert second_job_state["status"] == chat_store.BACKFILL_STATUS_COMPLETED
    assert second_job_state["processed_documents"] == 2

    after_second = {
        item["document_key"]: item
        for item in chat_store.list_documents(include_deleted=True, limit=100)
    }
    assert len(after_second) == 2

    for document_key, first_row in after_first.items():
        assert document_key in after_second
        second_row = after_second[document_key]
        assert int(second_row["id"]) == int(first_row["id"])
        assert int(second_row["chunk_count"]) == int(first_row["chunk_count"])

    assert refresh_calls["count"] == 2


def test_backfill_job_update_validation_and_noop(isolated_db):
    admin = chat_store.get_user_by_employee_id(chat_store.DEFAULT_ADMIN_EMPLOYEE_ID)
    assert admin is not None
    created = chat_store.create_backfill_job(created_by=int(admin["id"]))
    job_id = str(created["job_id"])

    assert chat_store.update_backfill_job(job_id) is False

    with pytest.raises(ValueError, match="Invalid backfill job status"):
        chat_store.update_backfill_job(job_id, status="invalid-status")
