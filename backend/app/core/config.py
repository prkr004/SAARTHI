"""Application settings for the FastAPI backend."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    api_name: str = "SAARTHI API"
    api_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    # Comma-separated origins for local web apps (e.g. Vite dev server).
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
    cors_allowed_methods: str = "GET,POST,PATCH,DELETE,OPTIONS"
    cors_allowed_headers: str = "Authorization,Content-Type,X-Request-Id"
    cors_expose_headers: str = "X-Request-Id,X-Process-Time-Ms"
    cors_allow_credentials: bool = True
    trusted_hosts: str = "localhost,127.0.0.1,testserver"

    access_token_ttl_minutes: int = Field(default=120, ge=5, le=1440)
    session_token_bytes: int = Field(default=48, ge=24, le=128)
    session_max_active_per_user: int = Field(default=5, ge=1, le=20)
    rag_request_timeout_seconds: int = Field(default=90, ge=10, le=300)
    fast_mode_request_timeout_seconds: int = Field(default=45, ge=5, le=180)
    temporal_request_timeout_seconds: int = Field(default=120, ge=10, le=420)
    readiness_require_vector_index: bool = False
    faiss_index_path: str = "faiss_index/index.faiss"
    hybrid_vector_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    hybrid_keyword_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    hybrid_candidate_multiplier: int = Field(default=4, ge=1, le=20)
    hybrid_keyword_min_token_length: int = Field(default=3, ge=1, le=20)

    admin_upload_directory: str = "data/admin_uploads"
    admin_upload_max_files_per_job: int = Field(default=12, ge=1, le=100)
    admin_upload_max_file_size_mb: int = Field(default=20, ge=1, le=200)
    admin_action_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    admin_action_rate_limit_max_requests: int = Field(default=60, ge=1, le=10000)

    document_summary_worker_enabled: bool = True
    document_summary_poll_interval_seconds: int = Field(default=30, ge=5, le=3600)
    document_summary_batch_size: int = Field(default=20, ge=1, le=500)
    document_summary_retry_after_seconds: int = Field(default=120, ge=0, le=86400)
    document_summary_retry_failed_enabled: bool = True

    notification_provider: Literal["noop", "console", "smtp", "gmail"] = "console"
    notification_from_email: str = "no-reply@saarthi.local"
    notification_smtp_host: str = "localhost"
    notification_smtp_port: int = Field(default=25, ge=1, le=65535)
    notification_smtp_username: str | None = None
    notification_smtp_password: str | None = None
    notification_smtp_use_ssl: bool = False
    notification_smtp_use_starttls: bool = False
    notification_smtp_timeout_seconds: int = Field(default=10, ge=1, le=60)
    notification_gmail_user: str | None = None
    notification_gmail_app_password: str | None = None

    include_internal_error_details: bool | None = None

    model_config = SettingsConfigDict(
        env_prefix="SAARTHI_",
        env_file=".env",
        extra="ignore",
    )

    @staticmethod
    def _csv(value: str) -> list[str]:
        parts = [entry.strip() for entry in value.split(",")]
        return [entry for entry in parts if entry]

    @model_validator(mode="after")
    def validate_security_options(self) -> "Settings":
        if self.cors_allow_credentials and "*" in self.cors_origins:
            raise ValueError("Wildcard CORS origins are not allowed when credentials are enabled.")
        if (self.hybrid_vector_weight + self.hybrid_keyword_weight) <= 0:
            raise ValueError("At least one hybrid retrieval weight must be greater than zero.")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return self._csv(self.cors_allowed_origins)

    @property
    def cors_methods(self) -> list[str]:
        return [item.upper() for item in self._csv(self.cors_allowed_methods)]

    @property
    def cors_headers(self) -> list[str]:
        return self._csv(self.cors_allowed_headers)

    @property
    def cors_exposed_headers(self) -> list[str]:
        return self._csv(self.cors_expose_headers)

    @property
    def trusted_hosts_list(self) -> list[str]:
        return self._csv(self.trusted_hosts)

    @property
    def expose_internal_error_details(self) -> bool:
        if self.include_internal_error_details is not None:
            return self.include_internal_error_details
        return self.environment in {"development", "test"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()


def load_settings() -> Settings:
    """Return a non-cached settings instance.

    Use this for components that should honor runtime env changes without
    requiring a process restart.
    """

    return Settings()
