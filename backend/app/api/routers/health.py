"""Basic health endpoints for local and deployment checks."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from chat_store import DB_PATH, initialize_db

from backend.app.core.config import get_settings
from backend.app.schemas.common import HealthStatus
from backend.app.services.auth_service import initialize_session_store

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthStatus)
def live() -> HealthStatus:
    settings = get_settings()
    return HealthStatus(
        status="ok",
        service=settings.api_name,
        version=settings.api_version,
        details={"environment": settings.environment},
    )


@router.get("/ready", response_model=HealthStatus)
def ready() -> HealthStatus:
    settings = get_settings()
    checks: dict[str, str] = {
        "database": "pending",
        "session_store": "pending",
        "vector_index": "skipped",
    }

    try:
        initialize_db()
        checks["database"] = "ok"

        if not DB_PATH.exists():
            raise RuntimeError(f"Database file missing at {DB_PATH}")

        initialize_session_store()
        checks["session_store"] = "ok"

        if settings.readiness_require_vector_index:
            vector_index = Path(settings.faiss_index_path)
            if not vector_index.exists():
                raise RuntimeError(f"Vector index missing at {vector_index}")
            checks["vector_index"] = "ok"
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Readiness checks failed: {exc}",
        ) from exc

    return HealthStatus(
        status="ready",
        service=settings.api_name,
        version=settings.api_version,
        details=checks,
    )
