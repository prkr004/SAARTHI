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

from dataclasses import dataclass, field, asdict
from typing import Optional


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
