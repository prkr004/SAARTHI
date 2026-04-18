"""Admin authorization, user review, and ingestion management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status

import chat_store
from backend.app.api.deps import get_admin_user
from backend.app.core.config import get_settings
from backend.app.schemas.admin import (
    AdminUserSummary,
    IngestionJobCreateResponse,
    IngestionJobListResponse,
    IngestionJobSummary,
    ReviewUserRequest,
    ReviewUserResponse,
    UserHistoryResponse,
)
from backend.app.services.admin_ingestion_service import persist_uploaded_pdfs, start_ingestion_job
from backend.app.services.notification_service import NotificationService
from backend.app.services.rate_limiter import allow_request

router = APIRouter(prefix="/admin", tags=["admin"])


def _enforce_admin_rate_limit(scope: str, current_admin: dict) -> None:
    settings = get_settings()
    actor_key = str(current_admin.get("user_id") or "unknown")
    allowed = allow_request(
        scope,
        actor_key,
        max_requests=settings.admin_action_rate_limit_max_requests,
        window_seconds=settings.admin_action_rate_limit_window_seconds,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for admin actions. Please retry shortly.",
        )


@router.get("/users/pending", response_model=list[AdminUserSummary])
def list_pending_users(current_admin: dict = Depends(get_admin_user)) -> list[AdminUserSummary]:
    _enforce_admin_rate_limit("admin_users_list", current_admin)

    users = chat_store.list_users_by_approval_status(chat_store.APPROVAL_PENDING)
    return [AdminUserSummary(**item) for item in users]


@router.get("/users/history", response_model=UserHistoryResponse)
def list_review_history(
    limit: int = Query(default=100, ge=1, le=500),
    current_admin: dict = Depends(get_admin_user),
) -> UserHistoryResponse:
    _enforce_admin_rate_limit("admin_users_history", current_admin)

    users = chat_store.list_review_history(limit=limit)
    return UserHistoryResponse(users=[AdminUserSummary(**item) for item in users])


@router.post("/users/{user_id}/approve", response_model=ReviewUserResponse)
def approve_user(
    user_id: int,
    payload: ReviewUserRequest,
    current_admin: dict = Depends(get_admin_user),
) -> ReviewUserResponse:
    _enforce_admin_rate_limit("admin_user_approve", current_admin)

    try:
        reviewed_user = chat_store.review_user_account(
            user_id=user_id,
            approval_status=chat_store.APPROVAL_APPROVED,
            reviewed_by=int(current_admin["user_id"]),
            review_reason=payload.review_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    notification_result = NotificationService().send_approval_email(
        recipient_email=reviewed_user.get("email"),
        full_name=str(reviewed_user.get("full_name") or "User"),
    )

    return ReviewUserResponse(
        message="User approved successfully.",
        user=AdminUserSummary(**reviewed_user),
        warning=notification_result.warning,
    )


@router.post("/users/{user_id}/reject", response_model=ReviewUserResponse)
def reject_user(
    user_id: int,
    payload: ReviewUserRequest,
    current_admin: dict = Depends(get_admin_user),
) -> ReviewUserResponse:
    _enforce_admin_rate_limit("admin_user_reject", current_admin)

    try:
        reviewed_user = chat_store.review_user_account(
            user_id=user_id,
            approval_status=chat_store.APPROVAL_REJECTED,
            reviewed_by=int(current_admin["user_id"]),
            review_reason=payload.review_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    notification_result = NotificationService().send_rejection_email(
        recipient_email=reviewed_user.get("email"),
        full_name=str(reviewed_user.get("full_name") or "User"),
        review_reason=payload.review_reason,
    )

    return ReviewUserResponse(
        message="User rejected successfully.",
        user=AdminUserSummary(**reviewed_user),
        warning=notification_result.warning,
    )


@router.post(
    "/ingestion/jobs",
    response_model=IngestionJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_ingestion_job(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    current_admin: dict = Depends(get_admin_user),
) -> IngestionJobCreateResponse:
    _enforce_admin_rate_limit("admin_ingestion_create", current_admin)

    try:
        stored_files = await persist_uploaded_pdfs(files)
        job = chat_store.create_ingestion_job(
            created_by=int(current_admin["user_id"]),
            total_files=len(stored_files),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    background_tasks.add_task(
        start_ingestion_job,
        job_id=str(job["job_id"]),
        stored_files=stored_files,
    )

    return IngestionJobCreateResponse(
        message="Ingestion job created.",
        job=IngestionJobSummary(**job),
    )


@router.get("/ingestion/jobs/{job_id}", response_model=IngestionJobSummary)
def get_ingestion_job_status(job_id: str, current_admin: dict = Depends(get_admin_user)) -> IngestionJobSummary:
    _enforce_admin_rate_limit("admin_ingestion_get", current_admin)

    job = chat_store.get_ingestion_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found.")

    return IngestionJobSummary(**job)


@router.get("/ingestion/jobs", response_model=IngestionJobListResponse)
def list_ingestion_jobs(
    limit: int = Query(default=20, ge=1, le=200),
    current_admin: dict = Depends(get_admin_user),
) -> IngestionJobListResponse:
    _enforce_admin_rate_limit("admin_ingestion_list", current_admin)

    jobs = chat_store.list_recent_ingestion_jobs(limit=limit)
    return IngestionJobListResponse(jobs=[IngestionJobSummary(**job) for job in jobs])
