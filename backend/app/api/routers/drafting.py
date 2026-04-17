"""Drafting endpoint for generating structured bank documents."""

from __future__ import annotations

import logging
import re
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from backend.app.api.deps import get_current_user
from backend.app.drafting.docx_export import create_docx
from backend.app.drafting.generator import generate_document
from backend.app.drafting.schema import draft_title
from backend.app.schemas.drafting import GenerateDocumentRequest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["drafting"])

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _slugify_filename(value: str, *, fallback: str = "document") -> str:
    cleaned = _FILENAME_SAFE_RE.sub("_", value).strip("._-")
    return cleaned or fallback


@router.post("/generate-document")
def generate_document_endpoint(
    payload: GenerateDocumentRequest,
    request: Request,
    _: dict = Depends(get_current_user),
) -> StreamingResponse:
    """Generate a regulated drafting document and return it as a DOCX file."""

    try:
        drafted_document = generate_document(
            document_type=payload.document_type,
            user_input={
                "query": payload.query,
                "audience": payload.audience,
            },
        )
        docx_bytes = create_docx(drafted_document)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Document generation failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception("Unexpected drafting failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while generating the document.",
        ) from exc

    filename = _slugify_filename(f"{drafted_document.document_type}_{draft_title(drafted_document)}")
    buffer = BytesIO(docx_bytes)
    buffer.seek(0)

    response = StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}.docx"'
    response.headers["X-Request-Id"] = getattr(request.state, "request_id", "")
    return response
