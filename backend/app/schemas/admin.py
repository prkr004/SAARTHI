"""Admin API request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.core.sanitization import sanitize_text

RoleLiteral = Literal["admin", "user"]
ApprovalStatusLiteral = Literal["pending", "approved", "rejected"]
IngestionStatusLiteral = Literal["queued", "running", "completed", "failed"]
BackfillStatusLiteral = Literal["queued", "running", "completed", "failed"]
DocumentSummaryStatusLiteral = Literal["pending", "running", "completed", "failed"]
SummaryJobStatusLiteral = Literal["queued", "running", "completed", "failed"]


class AdminUserSummary(BaseModel):
    id: int
    employee_id: str
    full_name: str
    email: str | None = None
    role: RoleLiteral
    approval_status: ApprovalStatusLiteral
    created_at: str
    reviewed_by: int | None = None
    reviewed_at: str | None = None
    review_reason: str | None = None
    reviewer_employee_id: str | None = None
    reviewer_name: str | None = None


class ReviewUserRequest(BaseModel):
    review_reason: str | None = Field(default=None, max_length=500)

    @field_validator("review_reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> str | None:
        if value is None:
            return None
        cleaned = sanitize_text(value, collapse_whitespace=True)
        return cleaned or None


class ReviewUserResponse(BaseModel):
    message: str
    user: AdminUserSummary
    warning: str | None = None


class GrantAccessRequest(BaseModel):
    employee_id: str = Field(min_length=4, max_length=24, pattern=r"^[A-Za-z0-9_-]+$")
    review_reason: str | None = Field(default=None, max_length=500)

    @field_validator("employee_id", mode="before")
    @classmethod
    def normalize_employee_id(cls, value: object) -> str:
        cleaned = sanitize_text(value, collapse_whitespace=True)
        if not cleaned:
            raise ValueError("Employee ID is required.")
        return cleaned

    @field_validator("review_reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> str | None:
        if value is None:
            return None
        cleaned = sanitize_text(value, collapse_whitespace=True)
        return cleaned or None


class IngestionJobSummary(BaseModel):
    job_id: str
    created_by: int
    created_by_employee_id: str | None = None
    created_by_name: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    status: IngestionStatusLiteral
    total_files: int
    processed_files: int
    total_chunks: int
    progress_percent: int
    current_file: str | None = None
    error_message: str | None = None


class IngestionJobCreateResponse(BaseModel):
    message: str
    job: IngestionJobSummary


class IngestionJobListResponse(BaseModel):
    jobs: list[IngestionJobSummary]


class BackfillJobCreateRequest(BaseModel):
    manifest_path: str | None = None

    @field_validator("manifest_path", mode="before")
    @classmethod
    def normalize_manifest_path(cls, value: object) -> str | None:
        if value is None:
            return None
        cleaned = sanitize_text(value, collapse_whitespace=True)
        return cleaned or None


class BackfillJobSummary(BaseModel):
    job_id: str
    created_by: int
    created_by_employee_id: str | None = None
    created_by_name: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    status: BackfillStatusLiteral
    total_documents: int
    processed_documents: int
    discovered_chunks: int
    progress_percent: int
    current_document_key: str | None = None
    error_message: str | None = None


class BackfillJobCreateResponse(BaseModel):
    message: str
    job: BackfillJobSummary


class BackfillJobListResponse(BaseModel):
    jobs: list[BackfillJobSummary]


class SummaryJobCreateRequest(BaseModel):
    include_failed: bool = True
    retry_after_seconds: int = Field(default=0, ge=0, le=86400)
    batch_size: int = Field(default=50, ge=1, le=500)


class SummaryJobSummary(BaseModel):
    job_id: str
    created_by: int
    created_by_employee_id: str | None = None
    created_by_name: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    status: SummaryJobStatusLiteral
    total_documents: int
    processed_documents: int
    completed_documents: int
    failed_documents: int
    include_failed: bool
    retry_after_seconds: int
    batch_size: int
    current_document_id: int | None = None
    error_message: str | None = None


class SummaryJobCreateResponse(BaseModel):
    message: str
    job: SummaryJobSummary


class SummaryJobListResponse(BaseModel):
    jobs: list[SummaryJobSummary]


class DocumentRegistryRecord(BaseModel):
    id: int
    document_key: str
    source: str
    document_title: str
    version_date: str | None = None
    effective_date: str | None = None
    regulator: str | None = None
    document_status: str | None = None
    chunk_count: int
    metadata: dict[str, Any] | None = None
    summary_status: DocumentSummaryStatusLiteral
    summary_one_liner: str | None = None
    summary_short: str | None = None
    summary_error: str | None = None
    summary_updated_at: str | None = None
    first_seen_at: str
    last_seen_at: str
    created_at: str
    updated_at: str
    last_ingestion_job_id: str | None = None
    is_deleted: int
    deleted_at: str | None = None
    deleted_by: int | None = None
    deleted_reason: str | None = None
    deleted_by_employee_id: str | None = None
    deleted_by_name: str | None = None


class DocumentRegistryListResponse(BaseModel):
    documents: list[DocumentRegistryRecord]
    total: int
    limit: int
    offset: int


class DocumentAuditLogEntry(BaseModel):
    id: int
    document_id: int
    event_type: str
    reason: str | None = None
    payload: dict[str, Any] | None = None
    actor_user_id: int | None = None
    actor_employee_id: str | None = None
    actor_name: str | None = None
    created_at: str


class DocumentDetailResponse(BaseModel):
    document: DocumentRegistryRecord
    audit_log: list[DocumentAuditLogEntry]


class DocumentMetadataUpdateRequest(BaseModel):
    source: str | None = None
    document_title: str | None = None
    version_date: str | None = None
    effective_date: str | None = None
    regulator: str | None = None
    document_status: str | None = None
    chunk_count: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = None
    last_ingestion_job_id: str | None = None

    @field_validator(
        "source",
        "document_title",
        "version_date",
        "effective_date",
        "regulator",
        "document_status",
        "last_ingestion_job_id",
        mode="before",
    )
    @classmethod
    def normalize_optional_text_fields(cls, value: object) -> str | None:
        if value is None:
            return None
        cleaned = sanitize_text(value, collapse_whitespace=True)
        return cleaned or None


class DocumentMetadataUpdateResponse(BaseModel):
    message: str
    document: DocumentRegistryRecord


class DocumentSoftDeleteRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> str | None:
        if value is None:
            return None
        cleaned = sanitize_text(value, collapse_whitespace=True)
        return cleaned or None


class DocumentSoftDeleteResponse(BaseModel):
    message: str
    document: DocumentRegistryRecord


class UserHistoryResponse(BaseModel):
    users: list[AdminUserSummary]


class ActiveUsersResponse(BaseModel):
    users: list[AdminUserSummary]
