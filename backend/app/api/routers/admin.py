"""Admin authorization, user review, and ingestion management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status

import chat_store
from backend.app.api.deps import get_admin_user
from backend.app.core.config import get_settings
from backend.app.schemas.admin import (
    ActiveUsersResponse,
    BackfillJobCreateRequest,
    BackfillJobCreateResponse,
    BackfillJobListResponse,
    BackfillJobSummary,
    AdminUserSummary,
    DocumentDetailResponse,
    DocumentMetadataUpdateRequest,
    DocumentMetadataUpdateResponse,
    DocumentRegistryListResponse,
    DocumentRegistryRecord,
    DocumentSoftDeleteRequest,
    DocumentSoftDeleteResponse,
    GrantAccessRequest,
    IngestionJobCreateResponse,
    IngestionJobListResponse,
    IngestionJobSummary,
    ReviewUserRequest,
    ReviewUserResponse,
    SummaryJobCreateRequest,
    SummaryJobCreateResponse,
    SummaryJobListResponse,
    SummaryJobSummary,
    UserHistoryResponse,
)
from backend.app.services.admin_ingestion_service import persist_uploaded_pdfs, start_ingestion_job
from backend.app.services.document_backfill_service import (
    DEFAULT_MANIFEST_PATH,
    start_document_backfill_job,
)
from backend.app.services.document_reindex_service import run_registry_reindex
from backend.app.services.document_summary_service import start_document_summary_job
from backend.app.services.notification_service import NotificationService
from backend.app.services.rag_cache_service import refresh_rag_caches
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


@router.get("/users/active", response_model=ActiveUsersResponse)
def list_active_users(current_admin: dict = Depends(get_admin_user)) -> ActiveUsersResponse:
    _enforce_admin_rate_limit("admin_users_active", current_admin)

    users = chat_store.list_active_users()
    return ActiveUsersResponse(users=[AdminUserSummary(**item) for item in users])


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


@router.post("/users/grant-access", response_model=ReviewUserResponse)
def grant_user_access(
    payload: GrantAccessRequest,
    current_admin: dict = Depends(get_admin_user),
) -> ReviewUserResponse:
    _enforce_admin_rate_limit("admin_user_grant_access", current_admin)

    try:
        reviewed_user = chat_store.grant_user_access_by_employee_id(
            employee_id=payload.employee_id,
            reviewed_by=int(current_admin["user_id"]),
            review_reason=payload.review_reason or "Access granted by admin.",
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
        message="Employee access granted successfully.",
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


@router.post("/users/{user_id}/revoke", response_model=ReviewUserResponse)
def revoke_user_access(
    user_id: int,
    payload: ReviewUserRequest,
    current_admin: dict = Depends(get_admin_user),
) -> ReviewUserResponse:
    _enforce_admin_rate_limit("admin_user_revoke", current_admin)

    try:
        reviewed_user = chat_store.review_user_account(
            user_id=user_id,
            approval_status=chat_store.APPROVAL_REJECTED,
            reviewed_by=int(current_admin["user_id"]),
            review_reason=payload.review_reason or "Access revoked by admin.",
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
        review_reason=payload.review_reason or "Access revoked by admin.",
    )

    return ReviewUserResponse(
        message="Employee access revoked successfully.",
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


@router.post(
    "/backfill/jobs",
    response_model=BackfillJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_backfill_job(
    payload: BackfillJobCreateRequest,
    background_tasks: BackgroundTasks,
    current_admin: dict = Depends(get_admin_user),
) -> BackfillJobCreateResponse:
    _enforce_admin_rate_limit("admin_backfill_create", current_admin)

    manifest_path = payload.manifest_path or str(DEFAULT_MANIFEST_PATH)
    job = chat_store.create_backfill_job(
        created_by=int(current_admin["user_id"]),
        total_documents=0,
    )

    background_tasks.add_task(
        start_document_backfill_job,
        job_id=str(job["job_id"]),
        manifest_path=manifest_path,
    )

    refreshed = chat_store.get_backfill_job(str(job["job_id"]))
    if refreshed is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load created backfill job.",
        )

    return BackfillJobCreateResponse(
        message="Backfill job created.",
        job=BackfillJobSummary(**refreshed),
    )


@router.get("/backfill/jobs/{job_id}", response_model=BackfillJobSummary)
def get_backfill_job_status(job_id: str, current_admin: dict = Depends(get_admin_user)) -> BackfillJobSummary:
    _enforce_admin_rate_limit("admin_backfill_get", current_admin)

    job = chat_store.get_backfill_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backfill job not found.")

    return BackfillJobSummary(**job)


@router.get("/backfill/jobs", response_model=BackfillJobListResponse)
def list_backfill_jobs(
    limit: int = Query(default=20, ge=1, le=200),
    current_admin: dict = Depends(get_admin_user),
) -> BackfillJobListResponse:
    _enforce_admin_rate_limit("admin_backfill_list", current_admin)

    jobs = chat_store.list_recent_backfill_jobs(limit=limit)
    return BackfillJobListResponse(jobs=[BackfillJobSummary(**job) for job in jobs])


@router.get("/documents", response_model=DocumentRegistryListResponse)
def list_documents(
    q: str | None = Query(default=None),
    summary_status: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    is_deleted: bool | None = Query(default=None),
    regulator: str | None = Query(default=None),
    document_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_admin: dict = Depends(get_admin_user),
) -> DocumentRegistryListResponse:
    _enforce_admin_rate_limit("admin_documents_list", current_admin)

    try:
        rows = chat_store.list_documents_for_admin(
            include_deleted=include_deleted,
            is_deleted=is_deleted,
            summary_status=summary_status,
            query_text=q,
            regulator=regulator,
            document_status=document_status,
            limit=limit,
            offset=offset,
        )
        total = chat_store.count_documents_for_admin(
            include_deleted=include_deleted,
            is_deleted=is_deleted,
            summary_status=summary_status,
            query_text=q,
            regulator=regulator,
            document_status=document_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return DocumentRegistryListResponse(
        documents=[DocumentRegistryRecord(**row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
def get_document_detail(
    document_id: int,
    audit_limit: int = Query(default=50, ge=1, le=500),
    current_admin: dict = Depends(get_admin_user),
) -> DocumentDetailResponse:
    _enforce_admin_rate_limit("admin_documents_get", current_admin)

    document = chat_store.get_document_by_id(document_id, include_deleted=True)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    audit_rows = chat_store.list_document_audit_log(document_id, limit=audit_limit)
    return DocumentDetailResponse(
        document=DocumentRegistryRecord(**document),
        audit_log=audit_rows,
    )


@router.patch("/documents/{document_id}", response_model=DocumentMetadataUpdateResponse)
def update_document_metadata(
    document_id: int,
    payload: DocumentMetadataUpdateRequest,
    background_tasks: BackgroundTasks,
    current_admin: dict = Depends(get_admin_user),
) -> DocumentMetadataUpdateResponse:
    _enforce_admin_rate_limit("admin_documents_update", current_admin)

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one metadata field must be provided.",
        )

    try:
        updated = chat_store.update_document_registry_metadata(
            document_id,
            actor_user_id=int(current_admin["user_id"]),
            audit_reason="Document metadata updated by admin endpoint.",
            **updates,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    refresh_rag_caches()
    background_tasks.add_task(
        run_registry_reindex,
        trigger="admin_documents_update",
        document_id=document_id,
        actor_user_id=int(current_admin["user_id"]),
    )

    document = chat_store.get_document_by_id(document_id, include_deleted=True)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    return DocumentMetadataUpdateResponse(
        message="Document metadata updated.",
        document=DocumentRegistryRecord(**document),
    )


@router.post("/documents/{document_id}/soft-delete", response_model=DocumentSoftDeleteResponse)
def soft_delete_document(
    document_id: int,
    payload: DocumentSoftDeleteRequest,
    background_tasks: BackgroundTasks,
    current_admin: dict = Depends(get_admin_user),
) -> DocumentSoftDeleteResponse:
    _enforce_admin_rate_limit("admin_documents_soft_delete", current_admin)

    deleted = chat_store.soft_delete_document(
        document_id,
        deleted_by=int(current_admin["user_id"]),
        deleted_reason=payload.reason,
        actor_user_id=int(current_admin["user_id"]),
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    refresh_rag_caches()
    background_tasks.add_task(
        run_registry_reindex,
        trigger="admin_documents_soft_delete",
        document_id=document_id,
        actor_user_id=int(current_admin["user_id"]),
    )

    document = chat_store.get_document_by_id(document_id, include_deleted=True)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    return DocumentSoftDeleteResponse(
        message="Document soft-deleted.",
        document=DocumentRegistryRecord(**document),
    )


@router.post(
    "/summary/jobs",
    response_model=SummaryJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_summary_job(
    payload: SummaryJobCreateRequest,
    background_tasks: BackgroundTasks,
    current_admin: dict = Depends(get_admin_user),
) -> SummaryJobCreateResponse:
    _enforce_admin_rate_limit("admin_summary_job_create", current_admin)

    total_documents = chat_store.count_documents_for_summary(
        include_failed=payload.include_failed,
        retry_after_seconds=payload.retry_after_seconds,
    )
    job = chat_store.create_summary_job(
        created_by=int(current_admin["user_id"]),
        include_failed=payload.include_failed,
        retry_after_seconds=payload.retry_after_seconds,
        batch_size=payload.batch_size,
        total_documents=total_documents,
    )

    background_tasks.add_task(
        start_document_summary_job,
        job_id=str(job["job_id"]),
        include_failed=payload.include_failed,
        retry_after_seconds=payload.retry_after_seconds,
        batch_size=payload.batch_size,
    )

    refreshed = chat_store.get_summary_job(str(job["job_id"]))
    if refreshed is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load created summary job.",
        )

    return SummaryJobCreateResponse(
        message="Summary job created.",
        job=SummaryJobSummary(**refreshed),
    )


@router.get("/summary/jobs/{job_id}", response_model=SummaryJobSummary)
def get_summary_job_status(job_id: str, current_admin: dict = Depends(get_admin_user)) -> SummaryJobSummary:
    _enforce_admin_rate_limit("admin_summary_job_get", current_admin)

    job = chat_store.get_summary_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary job not found.")

    return SummaryJobSummary(**job)


@router.get("/summary/jobs", response_model=SummaryJobListResponse)
def list_summary_jobs(
    limit: int = Query(default=20, ge=1, le=200),
    current_admin: dict = Depends(get_admin_user),
) -> SummaryJobListResponse:
    _enforce_admin_rate_limit("admin_summary_job_list", current_admin)

    jobs = chat_store.list_recent_summary_jobs(limit=limit)
    return SummaryJobListResponse(jobs=[SummaryJobSummary(**job) for job in jobs])
