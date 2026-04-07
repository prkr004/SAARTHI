"""Authentication request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.core.sanitization import sanitize_text


class RegisterRequest(BaseModel):
    employee_id: str = Field(min_length=4, max_length=24, pattern=r"^[A-Za-z0-9_-]+$")
    full_name: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=12, max_length=256)

    @field_validator("employee_id", mode="before")
    @classmethod
    def normalize_employee_id(cls, value: object) -> str:
        return sanitize_text(value, collapse_whitespace=True)

    @field_validator("full_name", mode="before")
    @classmethod
    def normalize_full_name(cls, value: object) -> str:
        cleaned = sanitize_text(value, collapse_whitespace=True)
        if len(cleaned) < 3:
            raise ValueError("Please enter your full name.")
        return cleaned


class LoginRequest(BaseModel):
    employee_id: str = Field(min_length=4, max_length=24)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("employee_id", mode="before")
    @classmethod
    def normalize_employee_id(cls, value: object) -> str:
        return sanitize_text(value, collapse_whitespace=True)


class UserProfile(BaseModel):
    user_id: int
    employee_id: str
    full_name: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserProfile
