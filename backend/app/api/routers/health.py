"""Basic health endpoints for local and deployment checks."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from chat_store import get_database_paths, initialize_db

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
        "employee_database": "pending",
        "admin_database": "pending",
        "session_store": "pending",
        "vector_index": "skipped",
    }

    try:
        initialize_db()
        db_paths = get_database_paths()
        employee_db = db_paths["employee"]
        admin_db = db_paths["admin"]
        session_db = db_paths["session"]

        if not employee_db.exists():
            raise RuntimeError(f"Employee database file missing at {employee_db}")
        if not admin_db.exists():
            raise RuntimeError(f"Admin database file missing at {admin_db}")

        checks["database"] = "ok"
        checks["employee_database"] = "ok"
        checks["admin_database"] = "ok"

        initialize_session_store()
        if not session_db.exists():
            raise RuntimeError(f"Session database file missing at {session_db}")
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
