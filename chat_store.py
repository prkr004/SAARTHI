"""
Secure local persistence for user accounts and chat conversations.

This module provides:
- employee authentication with PBKDF2 password hashing
- basic brute-force protection with temporary account lockout
- per-user conversation/message storage for chat resume
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac
from hmac import compare_digest
from pathlib import Path
from typing import Optional

DEFAULT_EMPLOYEE_DB_PATH = Path("data") / "shared" / "saarthi_employee.db"
DEFAULT_ADMIN_DB_PATH = Path("data") / "shared" / "saarthi_admin.db"
DEFAULT_SESSION_DB_PATH = Path("data") / "shared" / "saarthi_sessions.db"
LEGACY_DB_PATH = Path("data") / "saarthi_secure.db"

# Compatibility alias: tests and older code paths may monkeypatch this symbol.
DB_PATH = Path(os.getenv("SAARTHI_EMPLOYEE_DB_PATH", str(DEFAULT_EMPLOYEE_DB_PATH)))

PASSWORD_ITERATIONS = 240_000
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

_EMPLOYEE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{4,24}$")
_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
ADMIN_ID_ENV = "SAARTHI_ADMIN_EMPLOYEE_ID"
ADMIN_NAME_ENV = "SAARTHI_ADMIN_NAME"
ADMIN_PASSWORD_ENV = "SAARTHI_ADMIN_PASSWORD"
ADMIN_EMAIL_ENV = "SAARTHI_ADMIN_EMAIL"

DEFAULT_ADMIN_EMPLOYEE_ID = "ADMIN001"
DEFAULT_ADMIN_NAME = "Bank Admin"
DEFAULT_ADMIN_PASSWORD = "AdminPass#2026"

ROLE_ADMIN = "admin"
ROLE_USER = "user"

USER_SCOPE_EMPLOYEE = "employee"
USER_SCOPE_ADMIN = "admin"

APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"

REGISTRATION_PENDING_MESSAGE = "Your request has been sent to the admin. Once approved, you will have access to SAARTHI!"
PENDING_LOGIN_MESSAGE = "Your account is pending admin approval. Please wait for admin confirmation."
REJECTED_LOGIN_MESSAGE = "Your account request was rejected by the admin."

INGESTION_STATUS_QUEUED = "queued"
INGESTION_STATUS_RUNNING = "running"
INGESTION_STATUS_COMPLETED = "completed"
INGESTION_STATUS_FAILED = "failed"

BACKFILL_STATUS_QUEUED = "queued"
BACKFILL_STATUS_RUNNING = "running"
BACKFILL_STATUS_COMPLETED = "completed"
BACKFILL_STATUS_FAILED = "failed"

SUMMARY_JOB_STATUS_QUEUED = "queued"
SUMMARY_JOB_STATUS_RUNNING = "running"
SUMMARY_JOB_STATUS_COMPLETED = "completed"
SUMMARY_JOB_STATUS_FAILED = "failed"

DOCUMENT_SUMMARY_STATUS_PENDING = "pending"
DOCUMENT_SUMMARY_STATUS_RUNNING = "running"
DOCUMENT_SUMMARY_STATUS_COMPLETED = "completed"
DOCUMENT_SUMMARY_STATUS_FAILED = "failed"

DOCUMENT_AUDIT_EVENT_UPSERT_CREATED = "upsert_created"
DOCUMENT_AUDIT_EVENT_UPSERT_UPDATED = "upsert_updated"
DOCUMENT_AUDIT_EVENT_METADATA_UPDATED = "metadata_updated"
DOCUMENT_AUDIT_EVENT_SUMMARY_UPDATED = "summary_updated"
DOCUMENT_AUDIT_EVENT_SOFT_DELETED = "soft_deleted"

_UNSET = object()


@dataclass
class AuthResult:
    success: bool
    message: str
    user_id: Optional[int] = None
    employee_id: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    approval_status: Optional[str] = None
    email: Optional[str] = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _normalized_path(path_value: str | Path) -> Path:
    return Path(path_value)


def _employee_db_path() -> Path:
    return _normalized_path(DB_PATH)


def _derive_sibling_db_path(base_path: Path, suffix: str) -> Path:
    ext = base_path.suffix or ".db"
    return base_path.with_name(f"{base_path.stem}_{suffix}{ext}")


def _admin_db_path() -> Path:
    override = os.getenv("SAARTHI_ADMIN_DB_PATH")
    if override:
        return _normalized_path(override)

    employee_path = _employee_db_path()
    if employee_path == DEFAULT_EMPLOYEE_DB_PATH:
        return DEFAULT_ADMIN_DB_PATH
    return _derive_sibling_db_path(employee_path, "admin")


def _session_db_path() -> Path:
    override = os.getenv("SAARTHI_SESSION_DB_PATH")
    if override:
        return _normalized_path(override)

    employee_path = _employee_db_path()
    if employee_path == DEFAULT_EMPLOYEE_DB_PATH:
        return DEFAULT_SESSION_DB_PATH
    return _derive_sibling_db_path(employee_path, "sessions")


def get_database_paths() -> dict[str, Path]:
    return {
        "employee": _employee_db_path(),
        "admin": _admin_db_path(),
        "session": _session_db_path(),
        "legacy": LEGACY_DB_PATH,
    }


def get_session_db_path() -> Path:
    return _session_db_path()


def _open_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _employee_connection() -> sqlite3.Connection:
    return _open_connection(_employee_db_path())


def _admin_connection() -> sqlite3.Connection:
    return _open_connection(_admin_db_path())


def _connection() -> sqlite3.Connection:
    # Backward-compatible alias for existing code paths that operate on employee data.
    return _employee_connection()


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(row["name"]).lower() == column_name.lower() for row in rows)


def _users_table_has_reviewed_by_fk(conn: sqlite3.Connection) -> bool:
    rows = conn.execute("PRAGMA foreign_key_list(users)").fetchall()
    return any(str(row["from"]).lower() == "reviewed_by" for row in rows)


def _create_users_table_sql(*, include_reviewed_by_fk: bool) -> str:
    foreign_key_clause = ""
    if include_reviewed_by_fk:
        foreign_key_clause = ",\n                FOREIGN KEY(reviewed_by) REFERENCES users(id) ON DELETE SET NULL"

    return f"""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                approval_status TEXT NOT NULL DEFAULT 'pending',
                reviewed_by INTEGER,
                reviewed_at TEXT,
                review_reason TEXT,
                email TEXT,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT{foreign_key_clause}
            )
            """


def _rebuild_users_table_without_reviewed_by_fk(conn: sqlite3.Connection) -> None:
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute(
            _create_users_table_sql(include_reviewed_by_fk=False).replace(
                "CREATE TABLE IF NOT EXISTS users",
                "CREATE TABLE users_rebuild",
            )
        )
        conn.execute(
            """
            INSERT INTO users_rebuild (
                id,
                employee_id,
                full_name,
                password_hash,
                role,
                approval_status,
                reviewed_by,
                reviewed_at,
                review_reason,
                email,
                failed_attempts,
                locked_until,
                created_at,
                last_login
            )
            SELECT
                id,
                employee_id,
                full_name,
                password_hash,
                role,
                approval_status,
                reviewed_by,
                reviewed_at,
                review_reason,
                email,
                failed_attempts,
                locked_until,
                created_at,
                last_login
            FROM users
            """
        )
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_rebuild RENAME TO users")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _ensure_users_schema(conn: sqlite3.Connection) -> None:
    approval_column_added = False

    if not _column_exists(conn, "users", "role"):
        conn.execute(
            "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"
        )

    if not _column_exists(conn, "users", "approval_status"):
        conn.execute(
            "ALTER TABLE users ADD COLUMN approval_status TEXT NOT NULL DEFAULT 'pending'"
        )
        approval_column_added = True

    if not _column_exists(conn, "users", "reviewed_by"):
        conn.execute("ALTER TABLE users ADD COLUMN reviewed_by INTEGER")

    if not _column_exists(conn, "users", "reviewed_at"):
        conn.execute("ALTER TABLE users ADD COLUMN reviewed_at TEXT")

    if not _column_exists(conn, "users", "review_reason"):
        conn.execute("ALTER TABLE users ADD COLUMN review_reason TEXT")

    if not _column_exists(conn, "users", "email"):
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")

    conn.execute(
        """
        UPDATE users
        SET role = ?
        WHERE role IS NULL OR role NOT IN (?, ?)
        """,
        (ROLE_USER, ROLE_USER, ROLE_ADMIN),
    )

    conn.execute(
        """
        UPDATE users
        SET approval_status = ?
        WHERE approval_status IS NULL OR approval_status NOT IN (?, ?, ?)
        """,
        (
            APPROVAL_PENDING,
            APPROVAL_PENDING,
            APPROVAL_APPROVED,
            APPROVAL_REJECTED,
        ),
    )

    # Existing installations had no approval gate; preserve their ability to log in.
    if approval_column_added:
        conn.execute("UPDATE users SET approval_status = ?", (APPROVAL_APPROVED,))


def _ensure_ingestion_jobs_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ingestion_jobs (
            job_id TEXT PRIMARY KEY,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            status TEXT NOT NULL,
            total_files INTEGER NOT NULL DEFAULT 0,
            processed_files INTEGER NOT NULL DEFAULT 0,
            total_chunks INTEGER NOT NULL DEFAULT 0,
            progress_percent INTEGER NOT NULL DEFAULT 0,
            current_file TEXT,
            error_message TEXT,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE RESTRICT
        )
        """
    )

    if not _column_exists(conn, "ingestion_jobs", "updated_at"):
        conn.execute(
            "ALTER TABLE ingestion_jobs ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"
        )
    if not _column_exists(conn, "ingestion_jobs", "started_at"):
        conn.execute("ALTER TABLE ingestion_jobs ADD COLUMN started_at TEXT")
    if not _column_exists(conn, "ingestion_jobs", "completed_at"):
        conn.execute("ALTER TABLE ingestion_jobs ADD COLUMN completed_at TEXT")
    if not _column_exists(conn, "ingestion_jobs", "status"):
        conn.execute(
            "ALTER TABLE ingestion_jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'"
        )
    if not _column_exists(conn, "ingestion_jobs", "total_files"):
        conn.execute(
            "ALTER TABLE ingestion_jobs ADD COLUMN total_files INTEGER NOT NULL DEFAULT 0"
        )
    if not _column_exists(conn, "ingestion_jobs", "processed_files"):
        conn.execute(
            "ALTER TABLE ingestion_jobs ADD COLUMN processed_files INTEGER NOT NULL DEFAULT 0"
        )
    if not _column_exists(conn, "ingestion_jobs", "total_chunks"):
        conn.execute(
            "ALTER TABLE ingestion_jobs ADD COLUMN total_chunks INTEGER NOT NULL DEFAULT 0"
        )
    if not _column_exists(conn, "ingestion_jobs", "progress_percent"):
        conn.execute(
            "ALTER TABLE ingestion_jobs ADD COLUMN progress_percent INTEGER NOT NULL DEFAULT 0"
        )
    if not _column_exists(conn, "ingestion_jobs", "current_file"):
        conn.execute("ALTER TABLE ingestion_jobs ADD COLUMN current_file TEXT")
    if not _column_exists(conn, "ingestion_jobs", "error_message"):
        conn.execute("ALTER TABLE ingestion_jobs ADD COLUMN error_message TEXT")

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status_created
        ON ingestion_jobs(status, created_at DESC)
        """
    )


def _ensure_backfill_jobs_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS backfill_jobs (
            job_id TEXT PRIMARY KEY,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            status TEXT NOT NULL,
            total_documents INTEGER NOT NULL DEFAULT 0,
            processed_documents INTEGER NOT NULL DEFAULT 0,
            discovered_chunks INTEGER NOT NULL DEFAULT 0,
            progress_percent INTEGER NOT NULL DEFAULT 0,
            current_document_key TEXT,
            error_message TEXT,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE RESTRICT
        )
        """
    )

    if not _column_exists(conn, "backfill_jobs", "updated_at"):
        conn.execute(
            "ALTER TABLE backfill_jobs ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"
        )
    if not _column_exists(conn, "backfill_jobs", "started_at"):
        conn.execute("ALTER TABLE backfill_jobs ADD COLUMN started_at TEXT")
    if not _column_exists(conn, "backfill_jobs", "completed_at"):
        conn.execute("ALTER TABLE backfill_jobs ADD COLUMN completed_at TEXT")
    if not _column_exists(conn, "backfill_jobs", "status"):
        conn.execute(
            "ALTER TABLE backfill_jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'"
        )
    if not _column_exists(conn, "backfill_jobs", "total_documents"):
        conn.execute(
            "ALTER TABLE backfill_jobs ADD COLUMN total_documents INTEGER NOT NULL DEFAULT 0"
        )
    if not _column_exists(conn, "backfill_jobs", "processed_documents"):
        conn.execute(
            "ALTER TABLE backfill_jobs ADD COLUMN processed_documents INTEGER NOT NULL DEFAULT 0"
        )
    if not _column_exists(conn, "backfill_jobs", "discovered_chunks"):
        conn.execute(
            "ALTER TABLE backfill_jobs ADD COLUMN discovered_chunks INTEGER NOT NULL DEFAULT 0"
        )
    if not _column_exists(conn, "backfill_jobs", "progress_percent"):
        conn.execute(
            "ALTER TABLE backfill_jobs ADD COLUMN progress_percent INTEGER NOT NULL DEFAULT 0"
        )
    if not _column_exists(conn, "backfill_jobs", "current_document_key"):
        conn.execute("ALTER TABLE backfill_jobs ADD COLUMN current_document_key TEXT")
    if not _column_exists(conn, "backfill_jobs", "error_message"):
        conn.execute("ALTER TABLE backfill_jobs ADD COLUMN error_message TEXT")

    conn.execute(
        """
        UPDATE backfill_jobs
        SET total_documents = 0
        WHERE total_documents < 0
        """
    )
    conn.execute(
        """
        UPDATE backfill_jobs
        SET processed_documents = 0
        WHERE processed_documents < 0
        """
    )
    conn.execute(
        """
        UPDATE backfill_jobs
        SET discovered_chunks = 0
        WHERE discovered_chunks < 0
        """
    )
    conn.execute(
        """
        UPDATE backfill_jobs
        SET progress_percent = 0
        WHERE progress_percent < 0
        """
    )
    conn.execute(
        """
        UPDATE backfill_jobs
        SET progress_percent = 100
        WHERE progress_percent > 100
        """
    )
    conn.execute(
        """
        UPDATE backfill_jobs
        SET status = ?
        WHERE status IS NULL OR status NOT IN (?, ?, ?, ?)
        """,
        (
            BACKFILL_STATUS_QUEUED,
            BACKFILL_STATUS_QUEUED,
            BACKFILL_STATUS_RUNNING,
            BACKFILL_STATUS_COMPLETED,
            BACKFILL_STATUS_FAILED,
        ),
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_backfill_jobs_status_created
        ON backfill_jobs(status, created_at DESC)
        """
    )


def _ensure_summary_jobs_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS summary_jobs (
            job_id TEXT PRIMARY KEY,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            status TEXT NOT NULL,
            total_documents INTEGER NOT NULL DEFAULT 0,
            processed_documents INTEGER NOT NULL DEFAULT 0,
            completed_documents INTEGER NOT NULL DEFAULT 0,
            failed_documents INTEGER NOT NULL DEFAULT 0,
            include_failed INTEGER NOT NULL DEFAULT 1,
            retry_after_seconds INTEGER NOT NULL DEFAULT 0,
            batch_size INTEGER NOT NULL DEFAULT 0,
            current_document_id INTEGER,
            error_message TEXT,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE RESTRICT,
            FOREIGN KEY(current_document_id) REFERENCES documents(id) ON DELETE SET NULL
        )
        """
    )

    if not _column_exists(conn, "summary_jobs", "updated_at"):
        conn.execute("ALTER TABLE summary_jobs ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
    if not _column_exists(conn, "summary_jobs", "started_at"):
        conn.execute("ALTER TABLE summary_jobs ADD COLUMN started_at TEXT")
    if not _column_exists(conn, "summary_jobs", "completed_at"):
        conn.execute("ALTER TABLE summary_jobs ADD COLUMN completed_at TEXT")
    if not _column_exists(conn, "summary_jobs", "status"):
        conn.execute("ALTER TABLE summary_jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'")
    if not _column_exists(conn, "summary_jobs", "total_documents"):
        conn.execute("ALTER TABLE summary_jobs ADD COLUMN total_documents INTEGER NOT NULL DEFAULT 0")
    if not _column_exists(conn, "summary_jobs", "processed_documents"):
        conn.execute("ALTER TABLE summary_jobs ADD COLUMN processed_documents INTEGER NOT NULL DEFAULT 0")
    if not _column_exists(conn, "summary_jobs", "completed_documents"):
        conn.execute("ALTER TABLE summary_jobs ADD COLUMN completed_documents INTEGER NOT NULL DEFAULT 0")
    if not _column_exists(conn, "summary_jobs", "failed_documents"):
        conn.execute("ALTER TABLE summary_jobs ADD COLUMN failed_documents INTEGER NOT NULL DEFAULT 0")
    if not _column_exists(conn, "summary_jobs", "include_failed"):
        conn.execute("ALTER TABLE summary_jobs ADD COLUMN include_failed INTEGER NOT NULL DEFAULT 1")
    if not _column_exists(conn, "summary_jobs", "retry_after_seconds"):
        conn.execute("ALTER TABLE summary_jobs ADD COLUMN retry_after_seconds INTEGER NOT NULL DEFAULT 0")
    if not _column_exists(conn, "summary_jobs", "batch_size"):
        conn.execute("ALTER TABLE summary_jobs ADD COLUMN batch_size INTEGER NOT NULL DEFAULT 0")
    if not _column_exists(conn, "summary_jobs", "current_document_id"):
        conn.execute("ALTER TABLE summary_jobs ADD COLUMN current_document_id INTEGER")
    if not _column_exists(conn, "summary_jobs", "error_message"):
        conn.execute("ALTER TABLE summary_jobs ADD COLUMN error_message TEXT")

    conn.execute("UPDATE summary_jobs SET total_documents = 0 WHERE total_documents < 0")
    conn.execute("UPDATE summary_jobs SET processed_documents = 0 WHERE processed_documents < 0")
    conn.execute("UPDATE summary_jobs SET completed_documents = 0 WHERE completed_documents < 0")
    conn.execute("UPDATE summary_jobs SET failed_documents = 0 WHERE failed_documents < 0")
    conn.execute("UPDATE summary_jobs SET retry_after_seconds = 0 WHERE retry_after_seconds < 0")
    conn.execute("UPDATE summary_jobs SET batch_size = 0 WHERE batch_size < 0")
    conn.execute(
        """
        UPDATE summary_jobs
        SET include_failed = 1
        WHERE include_failed IS NULL OR include_failed NOT IN (0, 1)
        """
    )
    conn.execute(
        """
        UPDATE summary_jobs
        SET status = ?
        WHERE status IS NULL OR status NOT IN (?, ?, ?, ?)
        """,
        (
            SUMMARY_JOB_STATUS_QUEUED,
            SUMMARY_JOB_STATUS_QUEUED,
            SUMMARY_JOB_STATUS_RUNNING,
            SUMMARY_JOB_STATUS_COMPLETED,
            SUMMARY_JOB_STATUS_FAILED,
        ),
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_summary_jobs_status_created
        ON summary_jobs(status, created_at DESC)
        """
    )


def _ensure_documents_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_key TEXT NOT NULL,
            source TEXT NOT NULL,
            document_title TEXT NOT NULL,
            version_date TEXT,
            effective_date TEXT,
            regulator TEXT,
            document_status TEXT,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT,
            summary_status TEXT NOT NULL DEFAULT 'pending',
            summary_one_liner TEXT,
            summary_short TEXT,
            summary_error TEXT,
            summary_updated_at TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_ingestion_job_id TEXT,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT,
            deleted_by INTEGER,
            deleted_reason TEXT,
            FOREIGN KEY(last_ingestion_job_id) REFERENCES ingestion_jobs(job_id) ON DELETE SET NULL,
            FOREIGN KEY(deleted_by) REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )

    if not _column_exists(conn, "documents", "document_key"):
        conn.execute("ALTER TABLE documents ADD COLUMN document_key TEXT NOT NULL DEFAULT ''")
    if not _column_exists(conn, "documents", "source"):
        conn.execute("ALTER TABLE documents ADD COLUMN source TEXT NOT NULL DEFAULT ''")
    if not _column_exists(conn, "documents", "document_title"):
        conn.execute("ALTER TABLE documents ADD COLUMN document_title TEXT NOT NULL DEFAULT ''")
    if not _column_exists(conn, "documents", "version_date"):
        conn.execute("ALTER TABLE documents ADD COLUMN version_date TEXT")
    if not _column_exists(conn, "documents", "effective_date"):
        conn.execute("ALTER TABLE documents ADD COLUMN effective_date TEXT")
    if not _column_exists(conn, "documents", "regulator"):
        conn.execute("ALTER TABLE documents ADD COLUMN regulator TEXT")
    if not _column_exists(conn, "documents", "document_status"):
        conn.execute("ALTER TABLE documents ADD COLUMN document_status TEXT")
    if not _column_exists(conn, "documents", "chunk_count"):
        conn.execute("ALTER TABLE documents ADD COLUMN chunk_count INTEGER NOT NULL DEFAULT 0")
    if not _column_exists(conn, "documents", "metadata_json"):
        conn.execute("ALTER TABLE documents ADD COLUMN metadata_json TEXT")
    if not _column_exists(conn, "documents", "summary_status"):
        conn.execute(
            "ALTER TABLE documents ADD COLUMN summary_status TEXT NOT NULL DEFAULT 'pending'"
        )
    if not _column_exists(conn, "documents", "summary_one_liner"):
        conn.execute("ALTER TABLE documents ADD COLUMN summary_one_liner TEXT")
    if not _column_exists(conn, "documents", "summary_short"):
        conn.execute("ALTER TABLE documents ADD COLUMN summary_short TEXT")
    if not _column_exists(conn, "documents", "summary_error"):
        conn.execute("ALTER TABLE documents ADD COLUMN summary_error TEXT")
    if not _column_exists(conn, "documents", "summary_updated_at"):
        conn.execute("ALTER TABLE documents ADD COLUMN summary_updated_at TEXT")
    if not _column_exists(conn, "documents", "first_seen_at"):
        conn.execute("ALTER TABLE documents ADD COLUMN first_seen_at TEXT NOT NULL DEFAULT ''")
    if not _column_exists(conn, "documents", "last_seen_at"):
        conn.execute("ALTER TABLE documents ADD COLUMN last_seen_at TEXT NOT NULL DEFAULT ''")
    if not _column_exists(conn, "documents", "created_at"):
        conn.execute("ALTER TABLE documents ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
    if not _column_exists(conn, "documents", "updated_at"):
        conn.execute("ALTER TABLE documents ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
    if not _column_exists(conn, "documents", "last_ingestion_job_id"):
        conn.execute("ALTER TABLE documents ADD COLUMN last_ingestion_job_id TEXT")
    if not _column_exists(conn, "documents", "is_deleted"):
        conn.execute("ALTER TABLE documents ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0")
    if not _column_exists(conn, "documents", "deleted_at"):
        conn.execute("ALTER TABLE documents ADD COLUMN deleted_at TEXT")
    if not _column_exists(conn, "documents", "deleted_by"):
        conn.execute("ALTER TABLE documents ADD COLUMN deleted_by INTEGER")
    if not _column_exists(conn, "documents", "deleted_reason"):
        conn.execute("ALTER TABLE documents ADD COLUMN deleted_reason TEXT")

    now_iso = _utc_now_iso()
    conn.execute(
        """
        UPDATE documents
        SET created_at = ?
        WHERE created_at IS NULL OR TRIM(created_at) = ''
        """,
        (now_iso,),
    )
    conn.execute(
        """
        UPDATE documents
        SET updated_at = ?
        WHERE updated_at IS NULL OR TRIM(updated_at) = ''
        """,
        (now_iso,),
    )
    conn.execute(
        """
        UPDATE documents
        SET first_seen_at = ?
        WHERE first_seen_at IS NULL OR TRIM(first_seen_at) = ''
        """,
        (now_iso,),
    )
    conn.execute(
        """
        UPDATE documents
        SET last_seen_at = ?
        WHERE last_seen_at IS NULL OR TRIM(last_seen_at) = ''
        """,
        (now_iso,),
    )
    conn.execute(
        """
        UPDATE documents
        SET chunk_count = 0
        WHERE chunk_count < 0
        """
    )
    conn.execute(
        """
        UPDATE documents
        SET is_deleted = 0
        WHERE is_deleted IS NULL OR is_deleted NOT IN (0, 1)
        """
    )
    conn.execute(
        """
        UPDATE documents
        SET summary_status = ?
        WHERE summary_status IS NULL OR summary_status NOT IN (?, ?, ?, ?)
        """,
        (
            DOCUMENT_SUMMARY_STATUS_PENDING,
            DOCUMENT_SUMMARY_STATUS_PENDING,
            DOCUMENT_SUMMARY_STATUS_RUNNING,
            DOCUMENT_SUMMARY_STATUS_COMPLETED,
            DOCUMENT_SUMMARY_STATUS_FAILED,
        ),
    )
    conn.execute(
        """
        UPDATE documents
        SET document_key = source || '|' || document_title || '|' || COALESCE(version_date, '') || '|id:' || id
        WHERE document_key IS NULL OR TRIM(document_key) = ''
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_documents_key
        ON documents(document_key)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_documents_deleted_updated
        ON documents(is_deleted, updated_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_documents_summary_status
        ON documents(summary_status, updated_at DESC)
        """
    )


def _ensure_document_audit_log_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS document_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            reason TEXT,
            payload_json TEXT,
            actor_user_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY(actor_user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )

    if not _column_exists(conn, "document_audit_log", "document_id"):
        conn.execute("ALTER TABLE document_audit_log ADD COLUMN document_id INTEGER NOT NULL DEFAULT 0")
    if not _column_exists(conn, "document_audit_log", "event_type"):
        conn.execute("ALTER TABLE document_audit_log ADD COLUMN event_type TEXT NOT NULL DEFAULT ''")
    if not _column_exists(conn, "document_audit_log", "reason"):
        conn.execute("ALTER TABLE document_audit_log ADD COLUMN reason TEXT")
    if not _column_exists(conn, "document_audit_log", "payload_json"):
        conn.execute("ALTER TABLE document_audit_log ADD COLUMN payload_json TEXT")
    if not _column_exists(conn, "document_audit_log", "actor_user_id"):
        conn.execute("ALTER TABLE document_audit_log ADD COLUMN actor_user_id INTEGER")
    if not _column_exists(conn, "document_audit_log", "created_at"):
        conn.execute("ALTER TABLE document_audit_log ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")

    now_iso = _utc_now_iso()
    conn.execute(
        """
        UPDATE document_audit_log
        SET created_at = ?
        WHERE created_at IS NULL OR TRIM(created_at) = ''
        """,
        (now_iso,),
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_audit_log_document_created
        ON document_audit_log(document_id, created_at DESC)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_document_audit_log_event_created
        ON document_audit_log(event_type, created_at DESC)
        """
    )


def _normalize_optional_email(email: Optional[str]) -> Optional[str]:
    if email is None:
        return None
    cleaned = email.strip().lower()
    return cleaned or None


def _validate_email(email: Optional[str], *, required: bool) -> Optional[str]:
    normalized = _normalize_optional_email(email)
    if required and not normalized:
        return "Email address is required."
    if normalized and not _EMAIL_PATTERN.match(normalized):
        return "Please enter a valid email address."
    return None


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _ensure_users_table(conn: sqlite3.Connection, *, include_reviewed_by_fk: bool) -> None:
    conn.execute(_create_users_table_sql(include_reviewed_by_fk=include_reviewed_by_fk))
    _ensure_users_schema(conn)

    if not include_reviewed_by_fk and _users_table_has_reviewed_by_fk(conn):
        _rebuild_users_table_without_reviewed_by_fk(conn)

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_users_employee_id
        ON users(employee_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_users_approval_status
        ON users(approval_status)
        """
    )


def _ensure_employee_schema(conn: sqlite3.Connection) -> None:
    _ensure_users_table(conn, include_reviewed_by_fk=False)

    _ensure_conversation_schema(conn)


def _ensure_conversation_schema(conn: sqlite3.Connection) -> None:

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sources_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
        ON conversations(user_id, updated_at DESC)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_id
        ON messages(conversation_id, id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_messages_conversation_role
        ON messages(conversation_id, role)
        """
    )


def _ensure_admin_schema(conn: sqlite3.Connection) -> None:
    _ensure_users_table(conn, include_reviewed_by_fk=True)
    _ensure_conversation_schema(conn)
    _ensure_ingestion_jobs_schema(conn)
    _ensure_backfill_jobs_schema(conn)
    _ensure_documents_schema(conn)
    _ensure_summary_jobs_schema(conn)
    _ensure_document_audit_log_schema(conn)


def _copy_rows(
    source_conn: sqlite3.Connection,
    target_conn: sqlite3.Connection,
    table_name: str,
    columns: list[str],
    *,
    where_clause: Optional[str] = None,
    where_params: tuple[object, ...] = (),
) -> int:
    if not _table_exists(source_conn, table_name):
        return 0

    query = f"SELECT {', '.join(columns)} FROM {table_name}"
    if where_clause:
        query = f"{query} WHERE {where_clause}"

    rows = source_conn.execute(query, where_params).fetchall()
    if not rows:
        return 0

    placeholders = ", ".join("?" for _ in columns)
    insert_sql = (
        f"INSERT OR IGNORE INTO {table_name} ({', '.join(columns)}) "
        f"VALUES ({placeholders})"
    )

    inserted = 0
    for row in rows:
        target_conn.execute(insert_sql, tuple(row[column] for column in columns))
        inserted += 1
    return inserted


def _copy_user_rows(
    source_conn: sqlite3.Connection,
    target_conn: sqlite3.Connection,
    *,
    where_clause: Optional[str] = None,
    where_params: tuple[object, ...] = (),
) -> int:
    user_columns = [
        "id",
        "employee_id",
        "full_name",
        "password_hash",
        "role",
        "approval_status",
        "reviewed_by",
        "reviewed_at",
        "review_reason",
        "email",
        "failed_attempts",
        "locked_until",
        "created_at",
        "last_login",
    ]

    if not _table_exists(source_conn, "users"):
        return 0

    query = f"SELECT {', '.join(user_columns)} FROM users"
    if where_clause:
        query = f"{query} WHERE {where_clause}"

    rows = source_conn.execute(query, where_params).fetchall()
    if not rows:
        return 0

    placeholders = ", ".join("?" for _ in user_columns)
    insert_sql = (
        f"INSERT OR IGNORE INTO users ({', '.join(user_columns)}) "
        f"VALUES ({placeholders})"
    )

    inserted = 0
    for row in rows:
        payload = [row[column] for column in user_columns]
        payload[user_columns.index("reviewed_by")] = None
        target_conn.execute(insert_sql, payload)
        inserted += 1

    for row in rows:
        reviewer_id = row["reviewed_by"]
        if reviewer_id is None:
            continue
        reviewer_exists = target_conn.execute(
            "SELECT 1 FROM users WHERE id = ?",
            (int(reviewer_id),),
        ).fetchone()
        if reviewer_exists is None:
            continue
        target_conn.execute(
            "UPDATE users SET reviewed_by = ? WHERE id = ?",
            (int(reviewer_id), int(row["id"])),
        )

    return inserted


def _migrate_legacy_combined_database() -> None:
    employee_path = _employee_db_path()
    candidate_sources: list[Path] = []
    if employee_path == DEFAULT_EMPLOYEE_DB_PATH and LEGACY_DB_PATH != employee_path:
        candidate_sources.append(LEGACY_DB_PATH)
    candidate_sources.append(employee_path)

    with _admin_connection() as admin_conn:
        admin_has_documents = int(
            (
                admin_conn.execute("SELECT COUNT(1) AS total FROM documents").fetchone()["total"]
            )
            or 0
        ) > 0
        admin_has_ingestion_jobs = int(
            (
                admin_conn.execute("SELECT COUNT(1) AS total FROM ingestion_jobs").fetchone()["total"]
            )
            or 0
        ) > 0
        admin_has_backfill_jobs = int(
            (
                admin_conn.execute("SELECT COUNT(1) AS total FROM backfill_jobs").fetchone()["total"]
            )
            or 0
        ) > 0
        admin_has_summary_jobs = int(
            (
                admin_conn.execute("SELECT COUNT(1) AS total FROM summary_jobs").fetchone()["total"]
            )
            or 0
        ) > 0
    if admin_has_documents or admin_has_ingestion_jobs or admin_has_backfill_jobs or admin_has_summary_jobs:
        return

    source_path: Optional[Path] = None
    admin_tables = {
        "ingestion_jobs",
        "backfill_jobs",
        "summary_jobs",
        "documents",
        "document_audit_log",
    }
    for candidate_path in candidate_sources:
        if not candidate_path.exists():
            continue

        with _open_connection(candidate_path) as source_candidate_conn:
            if not _table_exists(source_candidate_conn, "users"):
                continue

            has_admin_users = int(
                (
                    source_candidate_conn.execute(
                        """
                        SELECT COUNT(1) AS total
                        FROM users
                        WHERE LOWER(COALESCE(role, 'user')) = 'admin'
                        """
                    ).fetchone()["total"]
                )
                or 0
            ) > 0
            has_admin_tables = any(_table_exists(source_candidate_conn, table) for table in admin_tables)

            if has_admin_users or has_admin_tables:
                source_path = candidate_path
                break

    if source_path is None:
        return

    with _open_connection(source_path) as source_conn:
        _ensure_employee_schema(source_conn)
        _ensure_admin_schema(source_conn)

        conversation_columns = ["id", "user_id", "title", "created_at", "updated_at"]
        message_columns = ["id", "conversation_id", "role", "content", "sources_json", "created_at"]

        ingestion_job_columns = [
            "job_id",
            "created_by",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
            "status",
            "total_files",
            "processed_files",
            "total_chunks",
            "progress_percent",
            "current_file",
            "error_message",
        ]
        backfill_job_columns = [
            "job_id",
            "created_by",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
            "status",
            "total_documents",
            "processed_documents",
            "discovered_chunks",
            "progress_percent",
            "current_document_key",
            "error_message",
        ]
        summary_job_columns = [
            "job_id",
            "created_by",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
            "status",
            "total_documents",
            "processed_documents",
            "completed_documents",
            "failed_documents",
            "include_failed",
            "retry_after_seconds",
            "batch_size",
            "current_document_id",
            "error_message",
        ]
        document_columns = [
            "id",
            "document_key",
            "source",
            "document_title",
            "version_date",
            "effective_date",
            "regulator",
            "document_status",
            "chunk_count",
            "metadata_json",
            "summary_status",
            "summary_one_liner",
            "summary_short",
            "summary_error",
            "summary_updated_at",
            "first_seen_at",
            "last_seen_at",
            "created_at",
            "updated_at",
            "last_ingestion_job_id",
            "is_deleted",
            "deleted_at",
            "deleted_by",
            "deleted_reason",
        ]
        document_audit_columns = [
            "id",
            "document_id",
            "event_type",
            "reason",
            "payload_json",
            "actor_user_id",
            "created_at",
        ]

        if source_path != employee_path:
            with _employee_connection() as employee_conn:
                _copy_user_rows(
                    source_conn,
                    employee_conn,
                    where_clause="LOWER(COALESCE(role, 'user')) != 'admin'",
                )
                _copy_rows(
                    source_conn,
                    employee_conn,
                    "conversations",
                    conversation_columns,
                    where_clause="user_id IN (SELECT id FROM users WHERE LOWER(COALESCE(role, 'user')) != 'admin')",
                )
                _copy_rows(
                    source_conn,
                    employee_conn,
                    "messages",
                    message_columns,
                    where_clause=(
                        "conversation_id IN ("
                        "SELECT c.id FROM conversations c "
                        "INNER JOIN users u ON u.id = c.user_id "
                        "WHERE LOWER(COALESCE(u.role, 'user')) != 'admin'"
                        ")"
                    ),
                )
                employee_conn.commit()

        with _admin_connection() as admin_conn:
            _copy_user_rows(
                source_conn,
                admin_conn,
            )
            _copy_rows(source_conn, admin_conn, "ingestion_jobs", ingestion_job_columns)
            _copy_rows(source_conn, admin_conn, "backfill_jobs", backfill_job_columns)
            _copy_rows(source_conn, admin_conn, "documents", document_columns)
            _copy_rows(source_conn, admin_conn, "summary_jobs", summary_job_columns)
            _copy_rows(source_conn, admin_conn, "document_audit_log", document_audit_columns)
            admin_conn.commit()


def initialize_db() -> None:
    with _employee_connection() as employee_conn:
        _ensure_employee_schema(employee_conn)
        employee_conn.commit()

    with _admin_connection() as admin_conn:
        _ensure_admin_schema(admin_conn)
        admin_conn.commit()

    _migrate_legacy_combined_database()


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"{PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        iterations_text, salt_hex, expected_hex = stored_hash.split("$", 2)
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(expected_hex)
    except (ValueError, TypeError):
        return False

    computed = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return compare_digest(computed, expected)


def _validate_registration(
    employee_id: str,
    full_name: str,
    password: str,
    email: Optional[str],
    *,
    require_email: bool,
) -> Optional[str]:
    if not _EMPLOYEE_ID_PATTERN.match(employee_id):
        return "Employee ID must be 4-24 chars and only use letters, digits, '_' or '-'."

    if len(full_name.strip()) < 3:
        return "Please enter your full name."

    if len(password) < 12:
        return "Password must be at least 12 characters long."

    checks = [
        any(ch.isupper() for ch in password),
        any(ch.islower() for ch in password),
        any(ch.isdigit() for ch in password),
        any(not ch.isalnum() for ch in password),
    ]
    if not all(checks):
        return "Password must include upper, lower, number, and special character."

    email_error = _validate_email(email, required=require_email)
    if email_error:
        return email_error

    return None


def register_user(
    employee_id: str,
    full_name: str,
    password: str,
    email: Optional[str] = None,
) -> AuthResult:
    employee_id = employee_id.strip()
    full_name = full_name.strip()
    normalized_email = _normalize_optional_email(email)

    validation_error = _validate_registration(
        employee_id,
        full_name,
        password,
        normalized_email,
        require_email=True,
    )
    if validation_error:
        return AuthResult(success=False, message=validation_error)

    if get_user_by_employee_id(employee_id, scope=USER_SCOPE_ADMIN) is not None:
        return AuthResult(success=False, message="An account with this Employee ID already exists.")

    with _employee_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO users (
                    employee_id,
                    full_name,
                    password_hash,
                    role,
                    approval_status,
                    email,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    employee_id,
                    full_name,
                    _hash_password(password),
                    ROLE_USER,
                    APPROVAL_PENDING,
                    normalized_email,
                    _utc_now_iso(),
                ),
            )
            conn.commit()
            return AuthResult(success=True, message=REGISTRATION_PENDING_MESSAGE)
        except sqlite3.IntegrityError:
            return AuthResult(success=False, message="An account with this Employee ID already exists.")


def authenticate_user(employee_id: str, password: str) -> AuthResult:
    employee_id = employee_id.strip()

    for user_scope, connection_factory in (
        (USER_SCOPE_EMPLOYEE, _employee_connection),
        (USER_SCOPE_ADMIN, _admin_connection),
    ):
        with connection_factory() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE employee_id = ?",
                (employee_id,),
            ).fetchone()

            if row is None:
                continue

            locked_until = row["locked_until"]
            if locked_until:
                lock_time = _parse_iso(locked_until)
                if lock_time > datetime.now(timezone.utc):
                    return AuthResult(
                        success=False,
                        message="Account temporarily locked due to repeated failed logins.",
                    )

            if not _verify_password(password, row["password_hash"]):
                failed_attempts = int(row["failed_attempts"]) + 1
                new_lock_time = None
                if failed_attempts >= MAX_FAILED_ATTEMPTS:
                    new_lock_time = (
                        datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
                    ).isoformat()
                    failed_attempts = 0

                conn.execute(
                    """
                    UPDATE users
                    SET failed_attempts = ?, locked_until = ?
                    WHERE id = ?
                    """,
                    (failed_attempts, new_lock_time, row["id"]),
                )
                conn.commit()
                return AuthResult(success=False, message="Employee ID or password is incorrect.")

            approval_status = str(row["approval_status"] or APPROVAL_PENDING)
            if approval_status == APPROVAL_PENDING:
                return AuthResult(
                    success=False,
                    message=PENDING_LOGIN_MESSAGE,
                    approval_status=APPROVAL_PENDING,
                )

            if approval_status == APPROVAL_REJECTED:
                review_reason = str(row["review_reason"] or "").strip()
                message = REJECTED_LOGIN_MESSAGE
                if review_reason:
                    message = f"{message} Reason: {review_reason}"
                return AuthResult(
                    success=False,
                    message=message,
                    approval_status=APPROVAL_REJECTED,
                )

            conn.execute(
                """
                UPDATE users
                SET failed_attempts = 0,
                    locked_until = NULL,
                    last_login = ?
                WHERE id = ?
                """,
                (_utc_now_iso(), row["id"]),
            )
            conn.commit()

            role = str(row["role"] or ROLE_USER)
            if user_scope == USER_SCOPE_ADMIN:
                role = ROLE_ADMIN

            return AuthResult(
                success=True,
                message="Login successful.",
                user_id=row["id"],
                employee_id=row["employee_id"],
                full_name=row["full_name"],
                role=role,
                approval_status=approval_status,
                email=row["email"],
            )

    return AuthResult(success=False, message="Employee ID or password is incorrect.")


def _validate_approval_status(approval_status: str) -> str:
    normalized = approval_status.strip().lower()
    if normalized not in {APPROVAL_PENDING, APPROVAL_APPROVED, APPROVAL_REJECTED}:
        raise ValueError("Invalid approval status.")
    return normalized


def _normalize_review_reason(reason: Optional[str]) -> Optional[str]:
    if reason is None:
        return None
    cleaned = " ".join(reason.split()).strip()
    return cleaned or None


def get_user_scope_for_role(role: Optional[str]) -> str:
    if str(role or "").strip().lower() == ROLE_ADMIN:
        return USER_SCOPE_ADMIN
    return USER_SCOPE_EMPLOYEE


def _normalize_user_scope(scope: Optional[str]) -> str:
    normalized = str(scope or "any").strip().lower()
    if normalized not in {"any", USER_SCOPE_EMPLOYEE, USER_SCOPE_ADMIN}:
        raise ValueError("Invalid user scope.")
    return normalized


def _resolve_admin_reviewer(reviewer_id: int) -> tuple[Optional[str], Optional[str]]:
    with _admin_connection() as conn:
        row = conn.execute(
            "SELECT employee_id, full_name FROM users WHERE id = ?",
            (int(reviewer_id),),
        ).fetchone()

    if row is None:
        return None, None
    return row["employee_id"], row["full_name"]


def _serialize_user_row(row: sqlite3.Row) -> dict:
    payload = dict(row)
    payload["id"] = int(payload["id"])
    payload["failed_attempts"] = int(payload.get("failed_attempts", 0) or 0)
    if payload.get("reviewed_by") is not None:
        payload["reviewed_by"] = int(payload["reviewed_by"])
        reviewer_employee_id, reviewer_name = _resolve_admin_reviewer(int(payload["reviewed_by"]))
        payload["reviewer_employee_id"] = reviewer_employee_id
        payload["reviewer_name"] = reviewer_name
    else:
        payload["reviewer_employee_id"] = None
        payload["reviewer_name"] = None
    return payload


def _get_user_by_id_from_store(user_id: int, *, scope: str) -> Optional[dict]:
    connection_factory = _admin_connection if scope == USER_SCOPE_ADMIN else _employee_connection
    with connection_factory() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if row is None:
        return None
    return _serialize_user_row(row)


def get_user_by_id(user_id: int, *, scope: str = "any") -> Optional[dict]:
    normalized_scope = _normalize_user_scope(scope)
    if normalized_scope == USER_SCOPE_EMPLOYEE:
        return _get_user_by_id_from_store(user_id, scope=USER_SCOPE_EMPLOYEE)
    if normalized_scope == USER_SCOPE_ADMIN:
        return _get_user_by_id_from_store(user_id, scope=USER_SCOPE_ADMIN)

    employee_row = _get_user_by_id_from_store(user_id, scope=USER_SCOPE_EMPLOYEE)
    if employee_row is not None:
        return employee_row
    return _get_user_by_id_from_store(user_id, scope=USER_SCOPE_ADMIN)


def _get_user_by_employee_id_from_store(employee_id: str, *, scope: str) -> Optional[dict]:
    connection_factory = _admin_connection if scope == USER_SCOPE_ADMIN else _employee_connection
    with connection_factory() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE employee_id = ?",
            (employee_id.strip(),),
        ).fetchone()
    if row is None:
        return None
    return _serialize_user_row(row)


def get_user_by_employee_id(employee_id: str, *, scope: str = "any") -> Optional[dict]:
    cleaned_id = employee_id.strip()
    normalized_scope = _normalize_user_scope(scope)
    if normalized_scope == USER_SCOPE_EMPLOYEE:
        return _get_user_by_employee_id_from_store(cleaned_id, scope=USER_SCOPE_EMPLOYEE)
    if normalized_scope == USER_SCOPE_ADMIN:
        return _get_user_by_employee_id_from_store(cleaned_id, scope=USER_SCOPE_ADMIN)

    employee_row = _get_user_by_employee_id_from_store(cleaned_id, scope=USER_SCOPE_EMPLOYEE)
    if employee_row is not None:
        return employee_row
    return _get_user_by_employee_id_from_store(cleaned_id, scope=USER_SCOPE_ADMIN)


def list_users_by_approval_status(approval_status: str, include_admin: bool = False) -> list[dict]:
    normalized_status = _validate_approval_status(approval_status)

    with _employee_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM users
            WHERE approval_status = ?
            ORDER BY created_at ASC
            """,
            (normalized_status,),
        ).fetchall()

    users = [_serialize_user_row(row) for row in rows]
    if not include_admin:
        return users

    with _admin_connection() as conn:
        admin_rows = conn.execute(
            """
            SELECT *
            FROM users
            WHERE role = ? AND approval_status = ?
            ORDER BY created_at ASC
            """,
            (ROLE_ADMIN, normalized_status),
        ).fetchall()

    merged = users + [_serialize_user_row(row) for row in admin_rows]
    merged.sort(key=lambda item: str(item.get("created_at") or ""))
    return merged


def list_review_history(limit: int = 100, include_admin: bool = False) -> list[dict]:
    safe_limit = max(1, min(limit, 500))

    with _employee_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM users
            WHERE approval_status IN (?, ?)
            ORDER BY COALESCE(reviewed_at, created_at) DESC
            LIMIT ?
            """,
            (APPROVAL_APPROVED, APPROVAL_REJECTED, safe_limit),
        ).fetchall()

    users = [_serialize_user_row(row) for row in rows]
    if not include_admin:
        return users

    with _admin_connection() as conn:
        admin_rows = conn.execute(
            """
            SELECT *
            FROM users
            WHERE role = ? AND approval_status IN (?, ?)
            ORDER BY COALESCE(reviewed_at, created_at) DESC
            LIMIT ?
            """,
            (ROLE_ADMIN, APPROVAL_APPROVED, APPROVAL_REJECTED, safe_limit),
        ).fetchall()

    merged = users + [_serialize_user_row(row) for row in admin_rows]
    merged.sort(
        key=lambda item: str(item.get("reviewed_at") or item.get("created_at") or ""),
        reverse=True,
    )
    return merged[:safe_limit]


def list_active_users(include_admin: bool = False) -> list[dict]:
    with _employee_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM users
            WHERE approval_status = ?
            ORDER BY full_name ASC
            """,
            (APPROVAL_APPROVED,),
        ).fetchall()

    users = [_serialize_user_row(row) for row in rows]
    if not include_admin:
        return users

    with _admin_connection() as conn:
        admin_rows = conn.execute(
            """
            SELECT *
            FROM users
            WHERE role = ? AND approval_status = ?
            ORDER BY full_name ASC
            """,
            (ROLE_ADMIN, APPROVAL_APPROVED),
        ).fetchall()

    merged = users + [_serialize_user_row(row) for row in admin_rows]
    merged.sort(key=lambda item: str(item.get("full_name") or "").lower())
    return merged


def review_user_account(
    user_id: int,
    approval_status: str,
    reviewed_by: int,
    review_reason: Optional[str] = None,
) -> dict:
    normalized_status = _validate_approval_status(approval_status)
    if normalized_status == APPROVAL_PENDING:
        raise ValueError("Review operation requires approved or rejected status.")

    normalized_reason = _normalize_review_reason(review_reason)

    with _employee_connection() as conn:
        target = conn.execute(
            "SELECT id, role FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if target is None:
            raise LookupError("User not found.")

        if str(target["role"] or ROLE_USER) == ROLE_ADMIN:
            raise PermissionError("Admin account status cannot be modified.")

        with _admin_connection() as admin_conn:
            reviewer = admin_conn.execute(
                "SELECT id, role FROM users WHERE id = ?",
                (reviewed_by,),
            ).fetchone()
            if reviewer is None:
                raise LookupError("Reviewer not found.")
            if str(reviewer["role"] or ROLE_USER) != ROLE_ADMIN:
                raise PermissionError("Only admins can review user accounts.")

        conn.execute(
            """
            UPDATE users
            SET approval_status = ?,
                reviewed_by = ?,
                reviewed_at = ?,
                review_reason = ?
            WHERE id = ?
            """,
            (
                normalized_status,
                reviewed_by,
                _utc_now_iso(),
                normalized_reason,
                user_id,
            ),
        )
        conn.commit()

    reviewed = get_user_by_id(user_id)
    if reviewed is None:
        raise LookupError("User not found after review update.")
    return reviewed


def grant_user_access_by_employee_id(
    employee_id: str,
    reviewed_by: int,
    review_reason: Optional[str] = None,
) -> dict:
    target = get_user_by_employee_id(employee_id)
    if target is None:
        raise LookupError("Employee was not found.")

    return review_user_account(
        user_id=int(target["id"]),
        approval_status=APPROVAL_APPROVED,
        reviewed_by=reviewed_by,
        review_reason=review_reason,
    )


def set_user_approval_status(
    employee_id: str,
    approval_status: str,
    reviewed_by: Optional[int] = None,
    review_reason: Optional[str] = None,
) -> bool:
    normalized_status = _validate_approval_status(approval_status)
    cleaned_employee_id = employee_id.strip()
    normalized_reason = _normalize_review_reason(review_reason)

    with _employee_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE users
            SET approval_status = ?,
                reviewed_by = ?,
                reviewed_at = ?,
                review_reason = ?
            WHERE employee_id = ?
            """,
            (
                normalized_status,
                reviewed_by,
                _utc_now_iso(),
                normalized_reason,
                cleaned_employee_id,
            ),
        )
        conn.commit()
        return cursor.rowcount > 0


def _normalize_ingestion_status(status_value: str) -> str:
    normalized = status_value.strip().lower()
    if normalized not in {
        INGESTION_STATUS_QUEUED,
        INGESTION_STATUS_RUNNING,
        INGESTION_STATUS_COMPLETED,
        INGESTION_STATUS_FAILED,
    }:
        raise ValueError("Invalid ingestion job status.")
    return normalized


def _serialize_ingestion_row(row: sqlite3.Row) -> dict:
    payload = dict(row)
    payload["total_files"] = int(payload.get("total_files", 0) or 0)
    payload["processed_files"] = int(payload.get("processed_files", 0) or 0)
    payload["total_chunks"] = int(payload.get("total_chunks", 0) or 0)
    payload["progress_percent"] = int(payload.get("progress_percent", 0) or 0)
    payload["created_by"] = int(payload["created_by"])
    return payload


def create_ingestion_job(created_by: int, total_files: int) -> dict:
    now_iso = _utc_now_iso()
    job_id = secrets.token_urlsafe(18)
    safe_total_files = max(0, int(total_files))

    with _admin_connection() as conn:
        conn.execute(
            """
            INSERT INTO ingestion_jobs (
                job_id,
                created_by,
                created_at,
                updated_at,
                started_at,
                completed_at,
                status,
                total_files,
                processed_files,
                total_chunks,
                progress_percent,
                current_file,
                error_message
            )
            VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, 0, 0, 0, NULL, NULL)
            """,
            (
                job_id,
                created_by,
                now_iso,
                now_iso,
                INGESTION_STATUS_QUEUED,
                safe_total_files,
            ),
        )
        conn.commit()

    created_job = get_ingestion_job(job_id)
    if created_job is None:
        raise RuntimeError("Failed to load created ingestion job.")
    return created_job


def get_ingestion_job(job_id: str) -> Optional[dict]:
    with _admin_connection() as conn:
        row = conn.execute(
            """
            SELECT j.*, u.employee_id AS created_by_employee_id, u.full_name AS created_by_name
            FROM ingestion_jobs j
            INNER JOIN users u ON u.id = j.created_by
            WHERE j.job_id = ?
            """,
            (job_id,),
        ).fetchone()

    if row is None:
        return None
    return _serialize_ingestion_row(row)


def list_recent_ingestion_jobs(limit: int = 20) -> list[dict]:
    safe_limit = max(1, min(limit, 200))
    with _admin_connection() as conn:
        rows = conn.execute(
            """
            SELECT j.*, u.employee_id AS created_by_employee_id, u.full_name AS created_by_name
            FROM ingestion_jobs j
            INNER JOIN users u ON u.id = j.created_by
            ORDER BY j.created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return [_serialize_ingestion_row(row) for row in rows]


def update_ingestion_job(
    job_id: str,
    *,
    status: object = _UNSET,
    processed_files: object = _UNSET,
    total_chunks: object = _UNSET,
    progress_percent: object = _UNSET,
    current_file: object = _UNSET,
    error_message: object = _UNSET,
    started_at: object = _UNSET,
    completed_at: object = _UNSET,
) -> bool:
    updates: dict[str, object] = {}

    if status is not _UNSET:
        updates["status"] = _normalize_ingestion_status(str(status))
    if processed_files is not _UNSET:
        updates["processed_files"] = max(0, int(processed_files))
    if total_chunks is not _UNSET:
        updates["total_chunks"] = max(0, int(total_chunks))
    if progress_percent is not _UNSET:
        updates["progress_percent"] = max(0, min(100, int(progress_percent)))
    if current_file is not _UNSET:
        updates["current_file"] = None if current_file is None else str(current_file)
    if error_message is not _UNSET:
        updates["error_message"] = None if error_message is None else str(error_message)
    if started_at is not _UNSET:
        updates["started_at"] = started_at
    if completed_at is not _UNSET:
        updates["completed_at"] = completed_at

    if not updates:
        return False

    updates["updated_at"] = _utc_now_iso()
    assignments = ", ".join(f"{column} = ?" for column in updates)
    params = list(updates.values())
    params.append(job_id)

    with _admin_connection() as conn:
        cursor = conn.execute(
            f"UPDATE ingestion_jobs SET {assignments} WHERE job_id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0


def _normalize_backfill_status(status_value: str) -> str:
    normalized = status_value.strip().lower()
    if normalized not in {
        BACKFILL_STATUS_QUEUED,
        BACKFILL_STATUS_RUNNING,
        BACKFILL_STATUS_COMPLETED,
        BACKFILL_STATUS_FAILED,
    }:
        raise ValueError("Invalid backfill job status.")
    return normalized


def _serialize_backfill_row(row: sqlite3.Row) -> dict:
    payload = dict(row)
    payload["created_by"] = int(payload["created_by"])
    payload["total_documents"] = int(payload.get("total_documents", 0) or 0)
    payload["processed_documents"] = int(payload.get("processed_documents", 0) or 0)
    payload["discovered_chunks"] = int(payload.get("discovered_chunks", 0) or 0)
    payload["progress_percent"] = int(payload.get("progress_percent", 0) or 0)
    return payload


def create_backfill_job(created_by: int, total_documents: int = 0) -> dict:
    now_iso = _utc_now_iso()
    job_id = secrets.token_urlsafe(18)
    safe_total_documents = max(0, int(total_documents))

    with _admin_connection() as conn:
        conn.execute(
            """
            INSERT INTO backfill_jobs (
                job_id,
                created_by,
                created_at,
                updated_at,
                started_at,
                completed_at,
                status,
                total_documents,
                processed_documents,
                discovered_chunks,
                progress_percent,
                current_document_key,
                error_message
            )
            VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, 0, 0, 0, NULL, NULL)
            """,
            (
                job_id,
                int(created_by),
                now_iso,
                now_iso,
                BACKFILL_STATUS_QUEUED,
                safe_total_documents,
            ),
        )
        conn.commit()

    created = get_backfill_job(job_id)
    if created is None:
        raise RuntimeError("Failed to load created backfill job.")
    return created


def get_backfill_job(job_id: str) -> Optional[dict]:
    with _admin_connection() as conn:
        row = conn.execute(
            """
            SELECT j.*, u.employee_id AS created_by_employee_id, u.full_name AS created_by_name
            FROM backfill_jobs j
            INNER JOIN users u ON u.id = j.created_by
            WHERE j.job_id = ?
            """,
            (job_id,),
        ).fetchone()

    if row is None:
        return None
    return _serialize_backfill_row(row)


def list_recent_backfill_jobs(limit: int = 20) -> list[dict]:
    safe_limit = max(1, min(limit, 200))
    with _admin_connection() as conn:
        rows = conn.execute(
            """
            SELECT j.*, u.employee_id AS created_by_employee_id, u.full_name AS created_by_name
            FROM backfill_jobs j
            INNER JOIN users u ON u.id = j.created_by
            ORDER BY j.created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return [_serialize_backfill_row(row) for row in rows]


def update_backfill_job(
    job_id: str,
    *,
    status: object = _UNSET,
    total_documents: object = _UNSET,
    processed_documents: object = _UNSET,
    discovered_chunks: object = _UNSET,
    progress_percent: object = _UNSET,
    current_document_key: object = _UNSET,
    error_message: object = _UNSET,
    started_at: object = _UNSET,
    completed_at: object = _UNSET,
) -> bool:
    updates: dict[str, object] = {}

    if status is not _UNSET:
        updates["status"] = _normalize_backfill_status(str(status))
    if total_documents is not _UNSET:
        updates["total_documents"] = max(0, int(total_documents))
    if processed_documents is not _UNSET:
        updates["processed_documents"] = max(0, int(processed_documents))
    if discovered_chunks is not _UNSET:
        updates["discovered_chunks"] = max(0, int(discovered_chunks))
    if progress_percent is not _UNSET:
        updates["progress_percent"] = max(0, min(100, int(progress_percent)))
    if current_document_key is not _UNSET:
        updates["current_document_key"] = (
            None if current_document_key is None else str(current_document_key)
        )
    if error_message is not _UNSET:
        updates["error_message"] = None if error_message is None else str(error_message)
    if started_at is not _UNSET:
        updates["started_at"] = started_at
    if completed_at is not _UNSET:
        updates["completed_at"] = completed_at

    if not updates:
        return False

    updates["updated_at"] = _utc_now_iso()
    assignments = ", ".join(f"{column} = ?" for column in updates)
    params = list(updates.values())
    params.append(job_id)

    with _admin_connection() as conn:
        cursor = conn.execute(
            f"UPDATE backfill_jobs SET {assignments} WHERE job_id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0


def _normalize_summary_job_status(status_value: str) -> str:
    normalized = status_value.strip().lower()
    if normalized not in {
        SUMMARY_JOB_STATUS_QUEUED,
        SUMMARY_JOB_STATUS_RUNNING,
        SUMMARY_JOB_STATUS_COMPLETED,
        SUMMARY_JOB_STATUS_FAILED,
    }:
        raise ValueError("Invalid summary job status.")
    return normalized


def _serialize_summary_job_row(row: sqlite3.Row) -> dict:
    payload = dict(row)
    payload["created_by"] = int(payload["created_by"])
    payload["total_documents"] = int(payload.get("total_documents", 0) or 0)
    payload["processed_documents"] = int(payload.get("processed_documents", 0) or 0)
    payload["completed_documents"] = int(payload.get("completed_documents", 0) or 0)
    payload["failed_documents"] = int(payload.get("failed_documents", 0) or 0)
    payload["retry_after_seconds"] = int(payload.get("retry_after_seconds", 0) or 0)
    payload["batch_size"] = int(payload.get("batch_size", 0) or 0)
    payload["include_failed"] = bool(int(payload.get("include_failed", 0) or 0))
    if payload.get("current_document_id") is not None:
        payload["current_document_id"] = int(payload["current_document_id"])
    return payload


def create_summary_job(
    *,
    created_by: int,
    include_failed: bool,
    retry_after_seconds: int,
    batch_size: int,
    total_documents: int = 0,
) -> dict:
    now_iso = _utc_now_iso()
    job_id = secrets.token_urlsafe(18)

    safe_total_documents = max(0, int(total_documents))
    safe_retry_after = max(0, int(retry_after_seconds))
    safe_batch_size = max(0, int(batch_size))

    with _admin_connection() as conn:
        conn.execute(
            """
            INSERT INTO summary_jobs (
                job_id,
                created_by,
                created_at,
                updated_at,
                started_at,
                completed_at,
                status,
                total_documents,
                processed_documents,
                completed_documents,
                failed_documents,
                include_failed,
                retry_after_seconds,
                batch_size,
                current_document_id,
                error_message
            )
            VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, 0, 0, 0, ?, ?, ?, NULL, NULL)
            """,
            (
                job_id,
                int(created_by),
                now_iso,
                now_iso,
                SUMMARY_JOB_STATUS_QUEUED,
                safe_total_documents,
                1 if include_failed else 0,
                safe_retry_after,
                safe_batch_size,
            ),
        )
        conn.commit()

    created = get_summary_job(job_id)
    if created is None:
        raise RuntimeError("Failed to load created summary job.")
    return created


def get_summary_job(job_id: str) -> Optional[dict]:
    with _admin_connection() as conn:
        row = conn.execute(
            """
            SELECT j.*, u.employee_id AS created_by_employee_id, u.full_name AS created_by_name
            FROM summary_jobs j
            INNER JOIN users u ON u.id = j.created_by
            WHERE j.job_id = ?
            """,
            (job_id,),
        ).fetchone()

    if row is None:
        return None
    return _serialize_summary_job_row(row)


def list_recent_summary_jobs(limit: int = 20) -> list[dict]:
    safe_limit = max(1, min(limit, 200))
    with _admin_connection() as conn:
        rows = conn.execute(
            """
            SELECT j.*, u.employee_id AS created_by_employee_id, u.full_name AS created_by_name
            FROM summary_jobs j
            INNER JOIN users u ON u.id = j.created_by
            ORDER BY j.created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return [_serialize_summary_job_row(row) for row in rows]


def update_summary_job(
    job_id: str,
    *,
    status: object = _UNSET,
    total_documents: object = _UNSET,
    processed_documents: object = _UNSET,
    completed_documents: object = _UNSET,
    failed_documents: object = _UNSET,
    include_failed: object = _UNSET,
    retry_after_seconds: object = _UNSET,
    batch_size: object = _UNSET,
    current_document_id: object = _UNSET,
    error_message: object = _UNSET,
    started_at: object = _UNSET,
    completed_at: object = _UNSET,
) -> bool:
    updates: dict[str, object] = {}

    if status is not _UNSET:
        updates["status"] = _normalize_summary_job_status(str(status))
    if total_documents is not _UNSET:
        updates["total_documents"] = max(0, int(total_documents))
    if processed_documents is not _UNSET:
        updates["processed_documents"] = max(0, int(processed_documents))
    if completed_documents is not _UNSET:
        updates["completed_documents"] = max(0, int(completed_documents))
    if failed_documents is not _UNSET:
        updates["failed_documents"] = max(0, int(failed_documents))
    if include_failed is not _UNSET:
        updates["include_failed"] = 1 if bool(include_failed) else 0
    if retry_after_seconds is not _UNSET:
        updates["retry_after_seconds"] = max(0, int(retry_after_seconds))
    if batch_size is not _UNSET:
        updates["batch_size"] = max(0, int(batch_size))
    if current_document_id is not _UNSET:
        updates["current_document_id"] = (
            None if current_document_id is None else int(current_document_id)
        )
    if error_message is not _UNSET:
        updates["error_message"] = None if error_message is None else str(error_message)
    if started_at is not _UNSET:
        updates["started_at"] = started_at
    if completed_at is not _UNSET:
        updates["completed_at"] = completed_at

    if not updates:
        return False

    updates["updated_at"] = _utc_now_iso()
    assignments = ", ".join(f"{column} = ?" for column in updates)
    params = list(updates.values())
    params.append(job_id)

    with _admin_connection() as conn:
        cursor = conn.execute(
            f"UPDATE summary_jobs SET {assignments} WHERE job_id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0


def count_documents_for_summary(*, include_failed: bool = True, retry_after_seconds: int = 300) -> int:
    safe_retry_after = max(0, int(retry_after_seconds))
    now = datetime.now(timezone.utc)
    failed_cutoff_iso = (now - timedelta(seconds=safe_retry_after)).isoformat()

    with _admin_connection() as conn:
        if include_failed:
            row = conn.execute(
                """
                SELECT COUNT(1) AS total
                FROM documents
                WHERE is_deleted = 0
                  AND (
                    summary_status = ?
                    OR (
                        summary_status = ?
                        AND (
                            summary_updated_at IS NULL
                            OR TRIM(summary_updated_at) = ''
                            OR summary_updated_at <= ?
                        )
                    )
                  )
                """,
                (
                    DOCUMENT_SUMMARY_STATUS_PENDING,
                    DOCUMENT_SUMMARY_STATUS_FAILED,
                    failed_cutoff_iso,
                ),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT COUNT(1) AS total
                FROM documents
                WHERE is_deleted = 0 AND summary_status = ?
                """,
                (DOCUMENT_SUMMARY_STATUS_PENDING,),
            ).fetchone()

    return int((row["total"] if row is not None else 0) or 0)


def _normalize_document_summary_status(summary_status: str) -> str:
    normalized = summary_status.strip().lower()
    if normalized not in {
        DOCUMENT_SUMMARY_STATUS_PENDING,
        DOCUMENT_SUMMARY_STATUS_RUNNING,
        DOCUMENT_SUMMARY_STATUS_COMPLETED,
        DOCUMENT_SUMMARY_STATUS_FAILED,
    }:
        raise ValueError("Invalid document summary status.")
    return normalized


def _normalize_document_key(document_key: Optional[str]) -> str:
    cleaned = (document_key or "").strip().lower()
    if not cleaned:
        raise ValueError("Document key is required.")
    return cleaned


def _build_document_key(*, source: str, document_title: str, version_date: Optional[str]) -> str:
    source_part = source.strip().lower()
    title_part = document_title.strip().lower()
    version_part = (version_date or "").strip().lower()
    return f"{source_part}|{title_part}|{version_part}"


def _normalize_document_required_text(value: Optional[str], *, field_name: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required.")
    return cleaned


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def _normalize_document_audit_event_type(event_type: str) -> str:
    normalized = event_type.strip().lower().replace(" ", "_")
    if not normalized:
        raise ValueError("Document audit event type is required.")
    return normalized


def _serialize_metadata_json(metadata: Optional[dict]) -> Optional[str]:
    if metadata is None:
        return None
    return json.dumps(metadata, sort_keys=True)


def _deserialize_metadata_json(payload: Optional[str]) -> Optional[dict]:
    if not payload:
        return None
    try:
        loaded = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if isinstance(loaded, dict):
        return loaded
    return None


def _serialize_document_row(row: sqlite3.Row) -> dict:
    payload = dict(row)
    payload["id"] = int(payload["id"])
    payload["chunk_count"] = int(payload.get("chunk_count", 0) or 0)
    payload["is_deleted"] = int(payload.get("is_deleted", 0) or 0)
    if payload.get("deleted_by") is not None:
        payload["deleted_by"] = int(payload["deleted_by"])
    payload["metadata"] = _deserialize_metadata_json(payload.get("metadata_json"))
    payload.pop("metadata_json", None)
    return payload


def _serialize_document_audit_row(row: sqlite3.Row) -> dict:
    payload = dict(row)
    payload["id"] = int(payload["id"])
    payload["document_id"] = int(payload["document_id"])
    if payload.get("actor_user_id") is not None:
        payload["actor_user_id"] = int(payload["actor_user_id"])

    payload_json = payload.get("payload_json")
    if payload_json:
        try:
            payload["payload"] = json.loads(payload_json)
        except json.JSONDecodeError:
            payload["payload"] = None
    else:
        payload["payload"] = None

    payload.pop("payload_json", None)
    return payload


def _append_document_audit_log_record(
    conn: sqlite3.Connection,
    *,
    document_id: int,
    event_type: str,
    actor_user_id: Optional[int] = None,
    reason: Optional[str] = None,
    payload: Optional[dict] = None,
) -> int:
    payload_json = json.dumps(payload, sort_keys=True) if payload is not None else None
    normalized_reason = _normalize_optional_text(reason)
    normalized_event_type = _normalize_document_audit_event_type(event_type)

    cursor = conn.execute(
        """
        INSERT INTO document_audit_log (
            document_id,
            event_type,
            reason,
            payload_json,
            actor_user_id,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            int(document_id),
            normalized_event_type,
            normalized_reason,
            payload_json,
            actor_user_id,
            _utc_now_iso(),
        ),
    )
    return int(cursor.lastrowid)


def append_document_audit_log(
    document_id: int,
    event_type: str,
    *,
    actor_user_id: Optional[int] = None,
    reason: Optional[str] = None,
    payload: Optional[dict] = None,
) -> int:
    with _admin_connection() as conn:
        row = conn.execute(
            "SELECT id FROM documents WHERE id = ?",
            (int(document_id),),
        ).fetchone()
        if row is None:
            raise LookupError("Document not found.")

        audit_id = _append_document_audit_log_record(
            conn,
            document_id=int(document_id),
            event_type=event_type,
            actor_user_id=actor_user_id,
            reason=reason,
            payload=payload,
        )
        conn.commit()
        return audit_id


def upsert_document_registry_entry(
    *,
    source: str,
    document_title: str,
    version_date: Optional[str] = None,
    effective_date: Optional[str] = None,
    regulator: Optional[str] = None,
    document_status: Optional[str] = None,
    chunk_count: int = 0,
    metadata: Optional[dict] = None,
    document_key: Optional[str] = None,
    last_ingestion_job_id: Optional[str] = None,
    actor_user_id: Optional[int] = None,
    audit_reason: Optional[str] = None,
) -> dict:
    normalized_source = _normalize_document_required_text(source, field_name="Source")
    normalized_title = _normalize_document_required_text(document_title, field_name="Document title")
    normalized_version_date = _normalize_optional_text(version_date)
    normalized_effective_date = _normalize_optional_text(effective_date)
    normalized_regulator = _normalize_optional_text(regulator)
    normalized_document_status = _normalize_optional_text(document_status)
    normalized_last_ingestion_job_id = _normalize_optional_text(last_ingestion_job_id)
    normalized_key = _normalize_document_key(
        document_key
        or _build_document_key(
            source=normalized_source,
            document_title=normalized_title,
            version_date=normalized_version_date,
        )
    )

    safe_chunk_count = max(0, int(chunk_count))
    metadata_json = _serialize_metadata_json(metadata)
    now_iso = _utc_now_iso()

    with _admin_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM documents WHERE document_key = ?",
            (normalized_key,),
        ).fetchone()

        if existing is None:
            cursor = conn.execute(
                """
                INSERT INTO documents (
                    document_key,
                    source,
                    document_title,
                    version_date,
                    effective_date,
                    regulator,
                    document_status,
                    chunk_count,
                    metadata_json,
                    summary_status,
                    summary_one_liner,
                    summary_short,
                    summary_error,
                    summary_updated_at,
                    first_seen_at,
                    last_seen_at,
                    created_at,
                    updated_at,
                    last_ingestion_job_id,
                    is_deleted,
                    deleted_at,
                    deleted_by,
                    deleted_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL)
                """,
                (
                    normalized_key,
                    normalized_source,
                    normalized_title,
                    normalized_version_date,
                    normalized_effective_date,
                    normalized_regulator,
                    normalized_document_status,
                    safe_chunk_count,
                    metadata_json,
                    DOCUMENT_SUMMARY_STATUS_PENDING,
                    now_iso,
                    now_iso,
                    now_iso,
                    now_iso,
                    normalized_last_ingestion_job_id,
                ),
            )
            document_id = int(cursor.lastrowid)
            event_type = DOCUMENT_AUDIT_EVENT_UPSERT_CREATED
        else:
            document_id = int(existing["id"])
            conn.execute(
                """
                UPDATE documents
                SET source = ?,
                    document_title = ?,
                    version_date = ?,
                    effective_date = ?,
                    regulator = ?,
                    document_status = ?,
                    chunk_count = ?,
                    metadata_json = ?,
                    last_seen_at = ?,
                    updated_at = ?,
                    last_ingestion_job_id = ?,
                    is_deleted = 0,
                    deleted_at = NULL,
                    deleted_by = NULL,
                    deleted_reason = NULL
                WHERE id = ?
                """,
                (
                    normalized_source,
                    normalized_title,
                    normalized_version_date,
                    normalized_effective_date,
                    normalized_regulator,
                    normalized_document_status,
                    safe_chunk_count,
                    metadata_json,
                    now_iso,
                    now_iso,
                    normalized_last_ingestion_job_id,
                    document_id,
                ),
            )
            event_type = DOCUMENT_AUDIT_EVENT_UPSERT_UPDATED

        _append_document_audit_log_record(
            conn,
            document_id=document_id,
            event_type=event_type,
            actor_user_id=actor_user_id,
            reason=audit_reason,
            payload={
                "document_key": normalized_key,
                "source": normalized_source,
                "document_title": normalized_title,
                "version_date": normalized_version_date,
                "effective_date": normalized_effective_date,
                "regulator": normalized_regulator,
                "document_status": normalized_document_status,
                "chunk_count": safe_chunk_count,
                "last_ingestion_job_id": normalized_last_ingestion_job_id,
            },
        )
        conn.commit()

    stored = get_document_by_id(document_id, include_deleted=True)
    if stored is None:
        raise RuntimeError("Document could not be loaded after upsert.")
    return stored


def get_document_by_id(document_id: int, *, include_deleted: bool = False) -> Optional[dict]:
    query = """
        SELECT d.*, deleter.employee_id AS deleted_by_employee_id, deleter.full_name AS deleted_by_name
        FROM documents d
        LEFT JOIN users deleter ON deleter.id = d.deleted_by
        WHERE d.id = ?
    """
    params: list[object] = [int(document_id)]

    if not include_deleted:
        query += " AND d.is_deleted = 0"

    with _admin_connection() as conn:
        row = conn.execute(query, params).fetchone()

    if row is None:
        return None
    return _serialize_document_row(row)


def get_document_by_key(document_key: str, *, include_deleted: bool = False) -> Optional[dict]:
    normalized_key = _normalize_document_key(document_key)
    query = """
        SELECT d.*, deleter.employee_id AS deleted_by_employee_id, deleter.full_name AS deleted_by_name
        FROM documents d
        LEFT JOIN users deleter ON deleter.id = d.deleted_by
        WHERE d.document_key = ?
    """
    params: list[object] = [normalized_key]

    if not include_deleted:
        query += " AND d.is_deleted = 0"

    with _admin_connection() as conn:
        row = conn.execute(query, params).fetchone()

    if row is None:
        return None
    return _serialize_document_row(row)


def list_documents(
    *,
    include_deleted: bool = False,
    summary_status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, int(offset))

    query = """
        SELECT d.*, deleter.employee_id AS deleted_by_employee_id, deleter.full_name AS deleted_by_name
        FROM documents d
        LEFT JOIN users deleter ON deleter.id = d.deleted_by
        WHERE 1 = 1
    """
    params: list[object] = []

    if not include_deleted:
        query += " AND d.is_deleted = 0"

    if summary_status is not None:
        normalized_summary_status = _normalize_document_summary_status(summary_status)
        query += " AND d.summary_status = ?"
        params.append(normalized_summary_status)

    query += " ORDER BY d.updated_at DESC, d.id DESC LIMIT ? OFFSET ?"
    params.extend([safe_limit, safe_offset])

    with _admin_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [_serialize_document_row(row) for row in rows]


def _apply_document_listing_filters(
    *,
    query_parts: list[str],
    params: list[object],
    include_deleted: bool,
    is_deleted: Optional[bool],
    summary_status: Optional[str],
    query_text: Optional[str],
    regulator: Optional[str],
    document_status: Optional[str],
) -> None:
    if is_deleted is None:
        if not include_deleted:
            query_parts.append(" AND d.is_deleted = 0")
    else:
        query_parts.append(" AND d.is_deleted = ?")
        params.append(1 if bool(is_deleted) else 0)

    if summary_status is not None:
        normalized_summary_status = _normalize_document_summary_status(summary_status)
        query_parts.append(" AND d.summary_status = ?")
        params.append(normalized_summary_status)

    normalized_query_text = _normalize_optional_text(query_text)
    if normalized_query_text:
        like_value = f"%{normalized_query_text.lower()}%"
        query_parts.append(
            """
            AND (
                LOWER(d.document_key) LIKE ?
                OR LOWER(d.source) LIKE ?
                OR LOWER(d.document_title) LIKE ?
                OR LOWER(COALESCE(d.regulator, '')) LIKE ?
            )
            """
        )
        params.extend([like_value, like_value, like_value, like_value])

    normalized_regulator = _normalize_optional_text(regulator)
    if normalized_regulator:
        params.append(f"%{normalized_regulator.lower()}%")
        query_parts.append(" AND LOWER(COALESCE(d.regulator, '')) LIKE ?")

    normalized_document_status = _normalize_optional_text(document_status)
    if normalized_document_status:
        params.append(f"%{normalized_document_status.lower()}%")
        query_parts.append(" AND LOWER(COALESCE(d.document_status, '')) LIKE ?")


def list_documents_for_admin(
    *,
    include_deleted: bool = False,
    is_deleted: Optional[bool] = None,
    summary_status: Optional[str] = None,
    query_text: Optional[str] = None,
    regulator: Optional[str] = None,
    document_status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    safe_limit = max(1, min(int(limit), 500))
    safe_offset = max(0, int(offset))

    query_parts = [
        """
        SELECT d.*, deleter.employee_id AS deleted_by_employee_id, deleter.full_name AS deleted_by_name
        FROM documents d
        LEFT JOIN users deleter ON deleter.id = d.deleted_by
        WHERE 1 = 1
        """
    ]
    params: list[object] = []

    _apply_document_listing_filters(
        query_parts=query_parts,
        params=params,
        include_deleted=include_deleted,
        is_deleted=is_deleted,
        summary_status=summary_status,
        query_text=query_text,
        regulator=regulator,
        document_status=document_status,
    )

    query_parts.append(" ORDER BY d.updated_at DESC, d.id DESC LIMIT ? OFFSET ?")
    params.extend([safe_limit, safe_offset])

    query = "".join(query_parts)
    with _admin_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [_serialize_document_row(row) for row in rows]


def count_documents_for_admin(
    *,
    include_deleted: bool = False,
    is_deleted: Optional[bool] = None,
    summary_status: Optional[str] = None,
    query_text: Optional[str] = None,
    regulator: Optional[str] = None,
    document_status: Optional[str] = None,
) -> int:
    query_parts = ["SELECT COUNT(1) AS total FROM documents d WHERE 1 = 1"]
    params: list[object] = []

    _apply_document_listing_filters(
        query_parts=query_parts,
        params=params,
        include_deleted=include_deleted,
        is_deleted=is_deleted,
        summary_status=summary_status,
        query_text=query_text,
        regulator=regulator,
        document_status=document_status,
    )

    query = "".join(query_parts)
    with _admin_connection() as conn:
        row = conn.execute(query, params).fetchone()

    return int((row["total"] if row is not None else 0) or 0)


def requeue_running_document_summaries(
    *,
    actor_user_id: Optional[int] = None,
    audit_reason: Optional[str] = None,
    recovery_error_message: Optional[str] = None,
) -> int:
    now_iso = _utc_now_iso()
    normalized_reason = _normalize_optional_text(audit_reason) or (
        "Summary worker recovery queued interrupted documents for retry."
    )
    normalized_recovery_error = _normalize_optional_text(recovery_error_message) or (
        "Previous summary run was interrupted and has been queued for retry."
    )

    updated_count = 0

    with _admin_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, summary_error
            FROM documents
            WHERE is_deleted = 0 AND summary_status = ?
            ORDER BY id ASC
            """,
            (DOCUMENT_SUMMARY_STATUS_RUNNING,),
        ).fetchall()

        for row in rows:
            document_id = int(row["id"])
            existing_error = _normalize_optional_text(row["summary_error"])
            effective_error = existing_error or normalized_recovery_error

            cursor = conn.execute(
                """
                UPDATE documents
                SET summary_status = ?,
                    summary_error = ?,
                    summary_updated_at = ?,
                    updated_at = ?
                WHERE id = ? AND is_deleted = 0 AND summary_status = ?
                """,
                (
                    DOCUMENT_SUMMARY_STATUS_PENDING,
                    effective_error,
                    now_iso,
                    now_iso,
                    document_id,
                    DOCUMENT_SUMMARY_STATUS_RUNNING,
                ),
            )

            if cursor.rowcount <= 0:
                continue

            _append_document_audit_log_record(
                conn,
                document_id=document_id,
                event_type=DOCUMENT_AUDIT_EVENT_SUMMARY_UPDATED,
                actor_user_id=actor_user_id,
                reason=normalized_reason,
                payload={
                    "updated_fields": ["summary_error", "summary_status"],
                    "from_status": DOCUMENT_SUMMARY_STATUS_RUNNING,
                    "to_status": DOCUMENT_SUMMARY_STATUS_PENDING,
                },
            )
            updated_count += 1

        conn.commit()

    return updated_count


def claim_next_document_for_summary(
    *,
    include_failed: bool = True,
    retry_after_seconds: int = 300,
    actor_user_id: Optional[int] = None,
    audit_reason: Optional[str] = None,
) -> Optional[dict]:
    safe_retry_after = max(0, int(retry_after_seconds))
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    failed_cutoff_iso = (now - timedelta(seconds=safe_retry_after)).isoformat()
    normalized_reason = _normalize_optional_text(audit_reason) or "Summary worker claimed document."

    with _admin_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")

        if include_failed:
            row = conn.execute(
                """
                SELECT id
                FROM documents
                WHERE is_deleted = 0
                  AND (
                    summary_status = ?
                    OR (
                        summary_status = ?
                        AND (
                            summary_updated_at IS NULL
                            OR TRIM(summary_updated_at) = ''
                            OR summary_updated_at <= ?
                        )
                    )
                  )
                ORDER BY
                    CASE summary_status
                        WHEN ? THEN 0
                        WHEN ? THEN 1
                        ELSE 2
                    END,
                    updated_at ASC,
                    id ASC
                LIMIT 1
                """,
                (
                    DOCUMENT_SUMMARY_STATUS_PENDING,
                    DOCUMENT_SUMMARY_STATUS_FAILED,
                    failed_cutoff_iso,
                    DOCUMENT_SUMMARY_STATUS_PENDING,
                    DOCUMENT_SUMMARY_STATUS_FAILED,
                ),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id
                FROM documents
                WHERE is_deleted = 0 AND summary_status = ?
                ORDER BY updated_at ASC, id ASC
                LIMIT 1
                """,
                (DOCUMENT_SUMMARY_STATUS_PENDING,),
            ).fetchone()

        if row is None:
            conn.commit()
            return None

        document_id = int(row["id"])
        cursor = conn.execute(
            """
            UPDATE documents
            SET summary_status = ?,
                summary_error = NULL,
                summary_updated_at = ?,
                updated_at = ?
            WHERE id = ?
              AND is_deleted = 0
              AND summary_status IN (?, ?)
            """,
            (
                DOCUMENT_SUMMARY_STATUS_RUNNING,
                now_iso,
                now_iso,
                document_id,
                DOCUMENT_SUMMARY_STATUS_PENDING,
                DOCUMENT_SUMMARY_STATUS_FAILED,
            ),
        )
        if cursor.rowcount <= 0:
            conn.commit()
            return None

        _append_document_audit_log_record(
            conn,
            document_id=document_id,
            event_type=DOCUMENT_AUDIT_EVENT_SUMMARY_UPDATED,
            actor_user_id=actor_user_id,
            reason=normalized_reason,
            payload={
                "updated_fields": ["summary_error", "summary_status"],
                "to_status": DOCUMENT_SUMMARY_STATUS_RUNNING,
            },
        )
        conn.commit()

    return get_document_by_id(document_id, include_deleted=True)


def update_document_registry_metadata(
    document_id: int,
    *,
    source: object = _UNSET,
    document_title: object = _UNSET,
    version_date: object = _UNSET,
    effective_date: object = _UNSET,
    regulator: object = _UNSET,
    document_status: object = _UNSET,
    chunk_count: object = _UNSET,
    metadata: object = _UNSET,
    last_ingestion_job_id: object = _UNSET,
    actor_user_id: Optional[int] = None,
    audit_reason: Optional[str] = None,
) -> bool:
    updates: dict[str, object] = {}

    if source is not _UNSET:
        updates["source"] = _normalize_document_required_text(
            None if source is None else str(source),
            field_name="Source",
        )
    if document_title is not _UNSET:
        updates["document_title"] = _normalize_document_required_text(
            None if document_title is None else str(document_title),
            field_name="Document title",
        )
    if version_date is not _UNSET:
        updates["version_date"] = _normalize_optional_text(None if version_date is None else str(version_date))
    if effective_date is not _UNSET:
        updates["effective_date"] = _normalize_optional_text(
            None if effective_date is None else str(effective_date)
        )
    if regulator is not _UNSET:
        updates["regulator"] = _normalize_optional_text(None if regulator is None else str(regulator))
    if document_status is not _UNSET:
        updates["document_status"] = _normalize_optional_text(
            None if document_status is None else str(document_status)
        )
    if chunk_count is not _UNSET:
        updates["chunk_count"] = max(0, int(chunk_count))
    if metadata is not _UNSET:
        if metadata is None:
            updates["metadata_json"] = None
        elif isinstance(metadata, dict):
            updates["metadata_json"] = _serialize_metadata_json(metadata)
        else:
            raise ValueError("Metadata must be a dictionary or None.")
    if last_ingestion_job_id is not _UNSET:
        updates["last_ingestion_job_id"] = _normalize_optional_text(
            None if last_ingestion_job_id is None else str(last_ingestion_job_id)
        )

    if not updates:
        return False

    updates["updated_at"] = _utc_now_iso()
    assignments = ", ".join(f"{column} = ?" for column in updates)
    params = list(updates.values())
    params.append(int(document_id))

    with _admin_connection() as conn:
        cursor = conn.execute(
            f"UPDATE documents SET {assignments} WHERE id = ? AND is_deleted = 0",
            params,
        )
        if cursor.rowcount <= 0:
            conn.commit()
            return False

        _append_document_audit_log_record(
            conn,
            document_id=int(document_id),
            event_type=DOCUMENT_AUDIT_EVENT_METADATA_UPDATED,
            actor_user_id=actor_user_id,
            reason=audit_reason,
            payload={"updated_fields": sorted(key for key in updates if key != "updated_at")},
        )
        conn.commit()
        return True


def update_document_summary(
    document_id: int,
    *,
    summary_status: object = _UNSET,
    summary_one_liner: object = _UNSET,
    summary_short: object = _UNSET,
    summary_error: object = _UNSET,
    actor_user_id: Optional[int] = None,
    audit_reason: Optional[str] = None,
) -> bool:
    updates: dict[str, object] = {}

    if summary_status is not _UNSET:
        updates["summary_status"] = _normalize_document_summary_status(str(summary_status))
    if summary_one_liner is not _UNSET:
        updates["summary_one_liner"] = _normalize_optional_text(
            None if summary_one_liner is None else str(summary_one_liner)
        )
    if summary_short is not _UNSET:
        updates["summary_short"] = _normalize_optional_text(
            None if summary_short is None else str(summary_short)
        )
    if summary_error is not _UNSET:
        updates["summary_error"] = _normalize_optional_text(
            None if summary_error is None else str(summary_error)
        )

    if not updates:
        return False

    now_iso = _utc_now_iso()
    updates["summary_updated_at"] = now_iso
    updates["updated_at"] = now_iso

    assignments = ", ".join(f"{column} = ?" for column in updates)
    params = list(updates.values())
    params.append(int(document_id))

    with _admin_connection() as conn:
        cursor = conn.execute(
            f"UPDATE documents SET {assignments} WHERE id = ? AND is_deleted = 0",
            params,
        )
        if cursor.rowcount <= 0:
            conn.commit()
            return False

        _append_document_audit_log_record(
            conn,
            document_id=int(document_id),
            event_type=DOCUMENT_AUDIT_EVENT_SUMMARY_UPDATED,
            actor_user_id=actor_user_id,
            reason=audit_reason,
            payload={"updated_fields": sorted(key for key in updates if key not in {"updated_at", "summary_updated_at"})},
        )
        conn.commit()
        return True


def soft_delete_document(
    document_id: int,
    *,
    deleted_by: Optional[int] = None,
    deleted_reason: Optional[str] = None,
    actor_user_id: Optional[int] = None,
) -> bool:
    now_iso = _utc_now_iso()
    normalized_reason = _normalize_optional_text(deleted_reason)

    with _admin_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE documents
            SET is_deleted = 1,
                deleted_at = ?,
                deleted_by = ?,
                deleted_reason = ?,
                updated_at = ?
            WHERE id = ? AND is_deleted = 0
            """,
            (
                now_iso,
                deleted_by,
                normalized_reason,
                now_iso,
                int(document_id),
            ),
        )

        if cursor.rowcount <= 0:
            conn.commit()
            return False

        _append_document_audit_log_record(
            conn,
            document_id=int(document_id),
            event_type=DOCUMENT_AUDIT_EVENT_SOFT_DELETED,
            actor_user_id=actor_user_id if actor_user_id is not None else deleted_by,
            reason=normalized_reason,
            payload={
                "deleted_by": deleted_by,
                "deleted_reason": normalized_reason,
            },
        )
        conn.commit()
        return True


def list_document_audit_log(document_id: int, *, limit: int = 100) -> list[dict]:
    safe_limit = max(1, min(limit, 500))
    with _admin_connection() as conn:
        rows = conn.execute(
            """
            SELECT a.*, actor.employee_id AS actor_employee_id, actor.full_name AS actor_name
            FROM document_audit_log a
            LEFT JOIN users actor ON actor.id = a.actor_user_id
            WHERE a.document_id = ?
            ORDER BY a.id DESC
            LIMIT ?
            """,
            (int(document_id), safe_limit),
        ).fetchall()

    return [_serialize_document_audit_row(row) for row in rows]


def create_conversation(user_id: int, title: str = "New Chat", *, scope: str = USER_SCOPE_EMPLOYEE) -> int:
    now = _utc_now_iso()
    with _conversation_connection(scope) as conn:
        cursor = conn.execute(
            """
            INSERT INTO conversations (user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, title, now, now),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_conversations(user_id: int, *, scope: str = USER_SCOPE_EMPLOYEE) -> list[dict]:
    with _conversation_connection(scope) as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (
                       SELECT COUNT(1)
                       FROM messages m
                       WHERE m.conversation_id = c.id
                   ) AS message_count
            FROM conversations c
            WHERE c.user_id = ?
            ORDER BY c.updated_at DESC
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def _assert_conversation_owner(conn: sqlite3.Connection, conversation_id: int, user_id: int) -> None:
    row = conn.execute(
        "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
        (conversation_id, user_id),
    ).fetchone()
    if row is None:
        raise PermissionError("Conversation access denied.")


def _conversation_connection(scope: str) -> sqlite3.Connection:
    normalized_scope = _normalize_user_scope(scope)
    if normalized_scope == USER_SCOPE_ADMIN:
        return _admin_connection()
    if normalized_scope == USER_SCOPE_EMPLOYEE:
        return _employee_connection()
    raise ValueError("Conversations require an explicit employee or admin scope.")


def add_message(
    conversation_id: int,
    user_id: int,
    role: str,
    content: str,
    sources: Optional[list[dict]] = None,
    *,
    scope: str = USER_SCOPE_EMPLOYEE,
) -> None:
    if role not in ("user", "assistant"):
        raise ValueError("Invalid message role.")

    with _conversation_connection(scope) as conn:
        _assert_conversation_owner(conn, conversation_id, user_id)

        conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, sources_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                role,
                content,
                json.dumps(sources or []),
                _utc_now_iso(),
            ),
        )

        if role == "user":
            first_user = conn.execute(
                """
                SELECT content
                FROM messages
                WHERE conversation_id = ? AND role = 'user'
                ORDER BY id ASC
                LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
            if first_user:
                title = (first_user["content"] or "New Chat").strip()[:80]
                conn.execute(
                    "UPDATE conversations SET title = ? WHERE id = ?",
                    (title or "New Chat", conversation_id),
                )

        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (_utc_now_iso(), conversation_id),
        )
        conn.commit()


def get_messages(conversation_id: int, user_id: int, *, scope: str = USER_SCOPE_EMPLOYEE) -> list[dict]:
    with _conversation_connection(scope) as conn:
        _assert_conversation_owner(conn, conversation_id, user_id)

        rows = conn.execute(
            """
            SELECT role, content, sources_json, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()

    messages: list[dict] = []
    for row in rows:
        sources = []
        if row["sources_json"]:
            try:
                sources = json.loads(row["sources_json"])
            except json.JSONDecodeError:
                sources = []
        messages.append(
            {
                "role": row["role"],
                "content": row["content"],
                "sources": sources,
            }
        )
    return messages


def ensure_user_has_conversation(user_id: int, *, scope: str = USER_SCOPE_EMPLOYEE) -> int:
    conversations = list_conversations(user_id, scope=scope)
    if conversations:
        return int(conversations[0]["id"])
    return create_conversation(user_id=user_id, title="New Chat", scope=scope)


def rename_conversation(
    conversation_id: int,
    user_id: int,
    new_title: str,
    *,
    scope: str = USER_SCOPE_EMPLOYEE,
) -> str:
    cleaned_title = " ".join((new_title or "").split()).strip()
    if not cleaned_title:
        raise ValueError("Chat title cannot be empty.")

    cleaned_title = cleaned_title[:80]

    with _conversation_connection(scope) as conn:
        _assert_conversation_owner(conn, conversation_id, user_id)
        conn.execute(
            """
            UPDATE conversations
            SET title = ?, updated_at = ?
            WHERE id = ?
            """,
            (cleaned_title, _utc_now_iso(), conversation_id),
        )
        conn.commit()

    return cleaned_title


def delete_conversation(conversation_id: int, user_id: int, *, scope: str = USER_SCOPE_EMPLOYEE) -> None:
    with _conversation_connection(scope) as conn:
        _assert_conversation_owner(conn, conversation_id, user_id)
        conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        conn.commit()


def bootstrap_admin_user() -> AuthResult:
    # Universal defaults ensure admin login works on any machine
    # even if environment variables are not configured.
    admin_employee_id = (os.getenv(ADMIN_ID_ENV) or DEFAULT_ADMIN_EMPLOYEE_ID).strip()
    admin_name = (os.getenv(ADMIN_NAME_ENV) or DEFAULT_ADMIN_NAME).strip()
    admin_password = os.getenv(ADMIN_PASSWORD_ENV) or DEFAULT_ADMIN_PASSWORD
    admin_email = _normalize_optional_email(os.getenv(ADMIN_EMAIL_ENV))

    validation_error = _validate_registration(
        admin_employee_id,
        admin_name,
        admin_password,
        admin_email,
        require_email=False,
    )
    if validation_error:
        return AuthResult(success=False, message=f"Admin bootstrap failed: {validation_error}")

    with _admin_connection() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE employee_id = ?",
            (admin_employee_id,),
        ).fetchone()

        if row is None:
            conn.execute(
                """
                INSERT INTO users (
                    employee_id,
                    full_name,
                    password_hash,
                    role,
                    approval_status,
                    reviewed_by,
                    reviewed_at,
                    review_reason,
                    email,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
                """,
                (
                    admin_employee_id,
                    admin_name,
                    _hash_password(admin_password),
                    ROLE_ADMIN,
                    APPROVAL_APPROVED,
                    admin_email,
                    _utc_now_iso(),
                ),
            )
            conn.commit()
            return AuthResult(success=True, message="Admin account created from environment variables.")

        needs_password_update = not _verify_password(admin_password, row["password_hash"])
        if needs_password_update:
            conn.execute(
                """
                UPDATE users
                SET full_name = ?,
                    password_hash = ?,
                    role = ?,
                    approval_status = ?,
                    reviewed_by = NULL,
                    reviewed_at = NULL,
                    review_reason = NULL,
                    email = ?,
                    failed_attempts = 0,
                    locked_until = NULL
                WHERE id = ?
                """,
                (
                    admin_name,
                    _hash_password(admin_password),
                    ROLE_ADMIN,
                    APPROVAL_APPROVED,
                    admin_email,
                    row["id"],
                ),
            )
            conn.commit()
            return AuthResult(success=True, message="Admin account updated from environment variables.")

        conn.execute(
            """
            UPDATE users
            SET full_name = ?,
                role = ?,
                approval_status = ?,
                reviewed_by = NULL,
                reviewed_at = NULL,
                review_reason = NULL,
                email = ?
            WHERE id = ?
            """,
            (
                admin_name,
                ROLE_ADMIN,
                APPROVAL_APPROVED,
                admin_email,
                row["id"],
            ),
        )
        conn.commit()
        return AuthResult(success=True, message="Admin account already configured.")
