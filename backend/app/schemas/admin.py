"""Admin API request/response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.core.sanitization import sanitize_text

RoleLiteral = Literal["admin", "user"]
ApprovalStatusLiteral = Literal["pending", "approved", "rejected"]
IngestionStatusLiteral = Literal["queued", "running", "completed", "failed"]


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


class UserHistoryResponse(BaseModel):
    users: list[AdminUserSummary]


class ActiveUsersResponse(BaseModel):
    users: list[AdminUserSummary]
