"""Manifest-driven corpus onboarding tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.vectorstore_builder import load_pdf_configs_from_manifest


def _make_entry(pdf_name: str = "sample.pdf") -> dict:
    return {
        "pdf_path": pdf_name,
        "regulator": "RBI",
        "document_title": "Sample Regulation",
        "version_date": "2024-01-01",
        "effective_date": "2024-01-01",
        "amends": None,
    }


def _write_manifest(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries), encoding="utf-8")


def test_manifest_missing_required_key_fails(tmp_path: Path):
    sample_pdf = tmp_path / "sample.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4\n")

    invalid_entry = _make_entry("sample.pdf")
    invalid_entry.pop("amends")

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, [invalid_entry])

    with pytest.raises(ValueError, match="missing required keys: amends"):
        load_pdf_configs_from_manifest(str(manifest_path))


def test_manifest_invalid_date_fails_with_clear_error(tmp_path: Path):
    sample_pdf = tmp_path / "sample.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4\n")

    invalid_entry = _make_entry("sample.pdf")
    invalid_entry["version_date"] = "01-01-2024"

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, [invalid_entry])

    with pytest.raises(ValueError, match="Expected format YYYY-MM-DD"):
        load_pdf_configs_from_manifest(str(manifest_path))


def test_manifest_allows_null_amends_and_resolves_relative_path(tmp_path: Path):
    sample_pdf = tmp_path / "sample.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4\n")

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, [_make_entry("sample.pdf")])

    configs = load_pdf_configs_from_manifest(str(manifest_path))

    assert len(configs) == 1
    assert configs[0]["amends"] is None
    assert Path(configs[0]["pdf_path"]).is_absolute()


def test_default_manifest_includes_rbi_sebi_and_dpdp_sources():
    manifest_path = Path("data/corpus_manifest.json")
    configs = load_pdf_configs_from_manifest(str(manifest_path))

    regulators = {cfg["regulator"] for cfg in configs}

    assert "RBI" in regulators
    assert "SEBI" in regulators
    assert "Government of India" in regulators
