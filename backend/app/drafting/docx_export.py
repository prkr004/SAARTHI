"""Word export helpers for the drafting module.

This module renders the structured drafting schema into a professional Word
document using python-docx. The exporter keeps formatting separate from the
generation logic so the drafting pipeline stays modular.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

from backend.app.drafting.schema import DocumentDraft, canonicalize_document_type

try:  # pragma: no cover - import guard for environments that have not installed the dependency yet
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt
except ImportError as exc:  # pragma: no cover - handled at runtime
    Document = None  # type: ignore[assignment]
    WD_ALIGN_PARAGRAPH = None  # type: ignore[assignment]
    OxmlElement = None  # type: ignore[assignment]
    qn = None  # type: ignore[assignment]
    Inches = None  # type: ignore[assignment]
    Pt = None  # type: ignore[assignment]
    _DOCX_IMPORT_ERROR = exc
else:
    _DOCX_IMPORT_ERROR = None

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def template_path(document_type: str) -> Path:
    """Return the on-disk template path for a supported document type."""

    normalized = canonicalize_document_type(document_type)
    return _TEMPLATE_DIR / f"{normalized}.txt"


def load_template_text(document_type: str) -> str:
    """Load the plain-text template associated with a document type."""

    path = template_path(document_type)
    if not path.exists():
        raise FileNotFoundError(f"Template file not found for document type '{document_type}'.")
    return path.read_text(encoding="utf-8")


def _coerce_document_draft(document_data: DocumentDraft | dict[str, Any]) -> DocumentDraft:
    if isinstance(document_data, DocumentDraft):
        return document_data
    return DocumentDraft.model_validate(document_data)


def _require_docx() -> None:
    if _DOCX_IMPORT_ERROR is not None:
        raise RuntimeError(
            "python-docx is required for DOCX export. Install the project dependencies first."
        ) from _DOCX_IMPORT_ERROR


def _set_paragraph_spacing(paragraph, *, before: int = 0, after: int = 0, line: float = 1.15) -> None:
    format_ = paragraph.paragraph_format
    format_.space_before = Pt(before)
    format_.space_after = Pt(after)
    format_.line_spacing = line


def _set_font(run, *, size: int = 11, bold: bool = False, italic: bool = False) -> None:
    run.font.name = "Calibri"
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    try:
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")  # type: ignore[union-attr]
    except Exception:
        pass


def _set_cell_text(cell, text: str, *, bold: bool = False, size: int = 10) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    run = paragraph.add_run(text)
    _set_font(run, size=size, bold=bold)


def _add_horizontal_rule(document) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("_" * 110)
    _set_font(run, size=8)
    _set_paragraph_spacing(paragraph, after=4)


def _apply_table_style(table) -> None:
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                _set_paragraph_spacing(paragraph, after=0)


def _configure_document(document) -> None:
    section = document.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.85)
    section.right_margin = Inches(0.85)

    styles = document.styles
    normal_style = styles["Normal"]
    normal_style.font.name = "Calibri"
    normal_style.font.size = Pt(11)


def _add_header(document, bank_name: str, export_date: date) -> None:
    header = document.sections[0].header
    paragraph = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(f"{bank_name} | {export_date:%d %b %Y}")
    _set_font(run, size=9, bold=True)
    _set_paragraph_spacing(paragraph, after=0)


def _add_title(document, title: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(title)
    _set_font(run, size=15, bold=True)
    _set_paragraph_spacing(paragraph, before=2, after=10)


def _iter_content_lines(content: Any) -> list[str]:
    if content is None:
        return []
    if isinstance(content, list):
        return [" ".join(str(item).split()) for item in content if str(item).strip()]

    text = str(content).strip()
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_bullet_line(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith(("- ", "• ", "* ")) or bool(stripped[:2].isdigit() and stripped[1:2] in {".", ")"})


def _clean_bullet_text(line: str) -> str:
    stripped = line.lstrip()
    if stripped.startswith(("- ", "• ", "* ")):
        return stripped[2:].strip()

    if len(stripped) >= 2 and stripped[0].isdigit():
        index = 1
        while index < len(stripped) and stripped[index].isdigit():
            index += 1
        if index < len(stripped) and stripped[index] in {".", ")"}:
            return stripped[index + 1 :].strip()
    return stripped


def _add_section_heading(document, heading: str) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(heading)
    _set_font(run, size=12, bold=True)
    _set_paragraph_spacing(paragraph, before=6, after=4)


def _add_body_paragraph(document, text: str) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    _set_font(run, size=11)
    _set_paragraph_spacing(paragraph, after=5)


def _add_bullet_paragraph(document, text: str, *, level: int = 0) -> None:
    paragraph = document.add_paragraph(style="List Bullet")
    if level > 0:
        paragraph.paragraph_format.left_indent = Inches(0.25 * level)
    run = paragraph.add_run(text)
    _set_font(run, size=11)
    _set_paragraph_spacing(paragraph, after=1)


def _add_section(document, section_data) -> None:
    _add_section_heading(document, section_data.heading)
    for line in _iter_content_lines(section_data.content):
        if _is_bullet_line(line):
            _add_bullet_paragraph(document, _clean_bullet_text(line))
        else:
            _add_body_paragraph(document, line)


def _add_references_section(document, references: list[str]) -> None:
    if not references:
        return

    _add_section_heading(document, "References")
    for reference in references:
        _add_bullet_paragraph(document, str(reference))


def _add_meta_table(document, *, document_type: str, export_date: date) -> None:
    table = document.add_table(rows=2, cols=2)
    table.style = "Table Grid"
    table.autofit = True

    _set_cell_text(table.cell(0, 0), "Document Type", bold=True)
    _set_cell_text(table.cell(0, 1), document_type.replace("_", " ").title())
    _set_cell_text(table.cell(1, 0), "Generated On", bold=True)
    _set_cell_text(table.cell(1, 1), export_date.strftime("%d %b %Y"))
    _apply_table_style(table)


def create_docx(document_data: DocumentDraft | dict[str, Any], *, bank_name: str = "SAARTHI") -> bytes:
    """Render structured document data into a DOCX binary payload."""

    _require_docx()
    draft = _coerce_document_draft(document_data)

    document = Document()
    _configure_document(document)

    today = date.today()
    _add_header(document, bank_name=bank_name, export_date=today)
    _add_title(document, draft.title)
    _add_meta_table(document, document_type=draft.document_type, export_date=today)
    _add_horizontal_rule(document)

    for section in draft.sections:
        _add_section(document, section)

    _add_references_section(document, draft.references)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def export_docx_preview(document_data: DocumentDraft | dict[str, Any]) -> str:
    """Render a simple text preview of the structured document output.

    This is intentionally lightweight scaffolding for the current phase. The
    full python-docx export routine will be introduced once generation is in
    place and the structure is stable.
    """

    draft = _coerce_document_draft(document_data)
    lines: list[str] = [draft.title, ""]

    for section in draft.sections:
        lines.append(section.heading)
        lines.append(section.content)
        lines.append("")

    if draft.references:
        lines.append("References")
        lines.extend(f"- {reference}" for reference in draft.references)

    return "\n".join(lines).strip()


def export_docx(document_data: DocumentDraft | dict[str, Any]) -> bytes:
    """Backward-compatible wrapper for the DOCX exporter."""

    return create_docx(document_data)
