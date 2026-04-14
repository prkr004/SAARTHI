"""
Metadata schema for regulatory document chunks.

Every chunk stored in the vector store carries this metadata so that
temporal / version-comparison queries can work reliably.

Fields
------
regulator       : str   – issuing body (e.g. "RBI", "SEBI")
document_title  : str   – canonical document name (used to link versions)
version_date    : str   – ISO-8601 date string (YYYY-MM-DD) of this version
effective_date  : str   – ISO-8601 date when the version became enforceable
status          : str   – "Active" or "Superseded"
amends          : str   – reference to the previous version (optional)
source          : str   – original file path
page            : int   – page number inside the PDF

Backward compatibility
----------------------
All temporal fields default to ``None`` so that documents indexed before
this module existed continue to work without errors.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping, Optional


REQUIRED_MANIFEST_KEYS: tuple[str, ...] = (
    "pdf_path",
    "regulator",
    "document_title",
    "version_date",
    "effective_date",
    "amends",
)

_ALLOWED_MANIFEST_OPTIONAL_KEYS: tuple[str, ...] = (
    "status",
    "chunk_size",
    "chunk_overlap",
)

_MANIFEST_ALLOWED_KEYS = set(REQUIRED_MANIFEST_KEYS) | set(_ALLOWED_MANIFEST_OPTIONAL_KEYS)
_ISO_DATE_FORMAT = "%Y-%m-%d"


@dataclass
class ChunkMetadata:
    """Structured metadata attached to every document chunk."""

    # --- original fields (always present) ---
    source: str = ""
    page: Optional[int] = None

    # --- temporal / regulatory fields (new) ---
    regulator: Optional[str] = None
    document_title: Optional[str] = None
    version_date: Optional[str] = None          # YYYY-MM-DD
    effective_date: Optional[str] = None         # YYYY-MM-DD
    status: Optional[str] = None                 # "Active" | "Superseded"
    amends: Optional[str] = None                 # free-text reference

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for LangChain Document metadata."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    @staticmethod
    def from_dict(raw: dict) -> "ChunkMetadata":
        """Build a ChunkMetadata from an existing metadata dict (safe for
        documents that were indexed before temporal fields existed)."""
        known_keys = {f.name for f in ChunkMetadata.__dataclass_fields__.values()}
        filtered = {k: v for k, v in raw.items() if k in known_keys}
        return ChunkMetadata(**filtered)


def _entry_label(entry_index: int | None) -> str:
    if entry_index is None:
        return "Manifest entry"
    return f"Manifest entry #{entry_index}"


def _require_non_empty_string(raw: Mapping[str, Any], key: str, label: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} has invalid '{key}'. Expected a non-empty string.")
    return value.strip()


def _require_iso_date(raw: Mapping[str, Any], key: str, label: str) -> str:
    value = _require_non_empty_string(raw, key, label)
    try:
        datetime.strptime(value, _ISO_DATE_FORMAT)
    except ValueError as exc:
        raise ValueError(
            f"{label} has invalid '{key}': '{value}'. Expected format YYYY-MM-DD."
        ) from exc
    return value


def validate_manifest_entry(raw: Mapping[str, Any], entry_index: int | None = None) -> dict:
    """Validate and normalize one manifest entry.

    Strict rules are applied for manifest ingestion only. Existing indexed
    metadata remains backward compatible through ``ChunkMetadata.from_dict``.
    """
    label = _entry_label(entry_index)

    if not isinstance(raw, Mapping):
        raise ValueError(f"{label} must be a JSON object.")

    missing = [key for key in REQUIRED_MANIFEST_KEYS if key not in raw]
    if missing:
        raise ValueError(f"{label} is missing required keys: {', '.join(missing)}")

    unknown = sorted(set(raw.keys()) - _MANIFEST_ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"{label} contains unsupported keys: {', '.join(unknown)}")

    normalized: dict[str, Any] = {
        "pdf_path": _require_non_empty_string(raw, "pdf_path", label),
        "regulator": _require_non_empty_string(raw, "regulator", label),
        "document_title": _require_non_empty_string(raw, "document_title", label),
        "version_date": _require_iso_date(raw, "version_date", label),
        "effective_date": _require_iso_date(raw, "effective_date", label),
    }

    amends_value = raw.get("amends")
    if amends_value is not None:
        if not isinstance(amends_value, str) or not amends_value.strip():
            raise ValueError(
                f"{label} has invalid 'amends'. Use null or a non-empty string reference."
            )
        normalized["amends"] = amends_value.strip()
    else:
        normalized["amends"] = None

    if "status" in raw and raw.get("status") is not None:
        normalized["status"] = _require_non_empty_string(raw, "status", label)

    if "chunk_size" in raw and raw.get("chunk_size") is not None:
        try:
            chunk_size = int(raw["chunk_size"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} has invalid 'chunk_size'. Expected a positive integer.") from exc
        if chunk_size <= 0:
            raise ValueError(f"{label} has invalid 'chunk_size'. Expected a positive integer.")
        normalized["chunk_size"] = chunk_size

    if "chunk_overlap" in raw and raw.get("chunk_overlap") is not None:
        try:
            chunk_overlap = int(raw["chunk_overlap"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{label} has invalid 'chunk_overlap'. Expected a non-negative integer."
            ) from exc
        if chunk_overlap < 0:
            raise ValueError(f"{label} has invalid 'chunk_overlap'. Expected a non-negative integer.")
        if "chunk_size" in normalized and chunk_overlap >= int(normalized["chunk_size"]):
            raise ValueError(
                f"{label} has invalid overlap configuration: chunk_overlap must be smaller than chunk_size."
            )
        normalized["chunk_overlap"] = chunk_overlap

    return normalized
