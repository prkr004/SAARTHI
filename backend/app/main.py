"""FastAPI app entry point for the migration backend."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from chat_store import bootstrap_admin_user, initialize_db

from backend.app.api.routers import admin, auth, chat, drafting, health, rag
from backend.app.core.config import get_settings
from backend.app.core.logging_config import configure_logging
from backend.app.services.auth_service import initialize_session_store, purge_expired_sessions
from backend.app.services.document_summary_service import (
    start_document_summary_worker,
    stop_document_summary_worker,
)

settings = get_settings()
configure_logging(settings.log_level, settings.log_format)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_db()
    bootstrap_result = bootstrap_admin_user()
    initialize_session_store()
    purged = purge_expired_sessions()
    summary_worker_started = start_document_summary_worker()

    logger.info(
        "Startup complete",
        extra={
            "environment": settings.environment,
            "admin_bootstrap": bootstrap_result.message,
            "purged_sessions": purged,
            "cors_origins": settings.cors_origins,
            "summary_worker_started": summary_worker_started,
        },
    )
    try:
        yield
    finally:
        summary_worker_stopped = stop_document_summary_worker()
        logger.info(
            "Shutdown complete",
            extra={
                "summary_worker_stopped": summary_worker_stopped,
            },
        )


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.api_name,
        version=settings.api_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_methods,
        allow_headers=settings.cors_headers,
        expose_headers=settings.cors_exposed_headers,
    )

    if settings.trusted_hosts_list:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts_list)

    @app.middleware("http")
    async def add_request_context(request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.exception(
                "Unhandled exception",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": str(request.url.path),
                },
            )

            detail = f"Internal server error. request_id={request_id}"
            if settings.expose_internal_error_details:
                detail = f"{detail}. reason={exc}"

            response = JSONResponse(status_code=500, content={"detail": detail})

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"

        if request.url.path.startswith(settings.api_prefix):
            response.headers["Cache-Control"] = "no-store"

        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": str(request.url.path),
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
            },
        )
        return response

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(admin.router, prefix=settings.api_prefix)
    app.include_router(chat.router, prefix=settings.api_prefix)
    app.include_router(drafting.router, prefix=settings.api_prefix)
    app.include_router(rag.router, prefix=settings.api_prefix)

    return app


app = create_app()
