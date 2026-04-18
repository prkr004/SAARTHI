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

DB_PATH = Path("data") / "saarthi_secure.db"

PASSWORD_ITERATIONS = 240_000
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

_EMPLOYEE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{4,24}$")
ADMIN_ID_ENV = "SAARTHI_ADMIN_EMPLOYEE_ID"
ADMIN_NAME_ENV = "SAARTHI_ADMIN_NAME"
ADMIN_PASSWORD_ENV = "SAARTHI_ADMIN_PASSWORD"
ADMIN_EMAIL_ENV = "SAARTHI_ADMIN_EMAIL"

DEFAULT_ADMIN_EMPLOYEE_ID = "ADMIN001"
DEFAULT_ADMIN_NAME = "Bank Admin"
DEFAULT_ADMIN_PASSWORD = "AdminPass#2026"

ROLE_ADMIN = "admin"
ROLE_USER = "user"

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


def _connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(row["name"]).lower() == column_name.lower() for row in rows)


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


def _normalize_optional_email(email: Optional[str]) -> Optional[str]:
    if email is None:
        return None
    cleaned = email.strip()
    return cleaned or None


def initialize_db() -> None:
    with _connection() as conn:
        conn.execute(
            """
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
                last_login TEXT,
                FOREIGN KEY(reviewed_by) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )

        _ensure_users_schema(conn)
        _ensure_ingestion_jobs_schema(conn)

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

        conn.commit()


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


def _validate_registration(employee_id: str, full_name: str, password: str) -> Optional[str]:
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

    validation_error = _validate_registration(employee_id, full_name, password)
    if validation_error:
        return AuthResult(success=False, message=validation_error)

    with _connection() as conn:
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
            return AuthResult(success=False, message="Employee ID already exists.")


def authenticate_user(employee_id: str, password: str) -> AuthResult:
    employee_id = employee_id.strip()

    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE employee_id = ?",
            (employee_id,),
        ).fetchone()

        if row is None:
            return AuthResult(success=False, message="Invalid credentials.")

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
                new_lock_time = (datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
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
            return AuthResult(success=False, message="Invalid credentials.")

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

        return AuthResult(
            success=True,
            message="Login successful.",
            user_id=row["id"],
            employee_id=row["employee_id"],
            full_name=row["full_name"],
            role=str(row["role"] or ROLE_USER),
            approval_status=approval_status,
            email=row["email"],
        )


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


def _serialize_user_row(row: sqlite3.Row) -> dict:
    payload = dict(row)
    payload["id"] = int(payload["id"])
    payload["failed_attempts"] = int(payload.get("failed_attempts", 0) or 0)
    if payload.get("reviewed_by") is not None:
        payload["reviewed_by"] = int(payload["reviewed_by"])
    return payload


def get_user_by_id(user_id: int) -> Optional[dict]:
    with _connection() as conn:
        row = conn.execute(
            """
            SELECT u.*, reviewer.employee_id AS reviewer_employee_id, reviewer.full_name AS reviewer_name
            FROM users u
            LEFT JOIN users reviewer ON reviewer.id = u.reviewed_by
            WHERE u.id = ?
            """,
            (user_id,),
        ).fetchone()

    if row is None:
        return None
    return _serialize_user_row(row)


def get_user_by_employee_id(employee_id: str) -> Optional[dict]:
    cleaned_id = employee_id.strip()
    with _connection() as conn:
        row = conn.execute(
            """
            SELECT u.*, reviewer.employee_id AS reviewer_employee_id, reviewer.full_name AS reviewer_name
            FROM users u
            LEFT JOIN users reviewer ON reviewer.id = u.reviewed_by
            WHERE u.employee_id = ?
            """,
            (cleaned_id,),
        ).fetchone()

    if row is None:
        return None
    return _serialize_user_row(row)


def list_users_by_approval_status(approval_status: str, include_admin: bool = False) -> list[dict]:
    normalized_status = _validate_approval_status(approval_status)

    query = """
        SELECT u.*, reviewer.employee_id AS reviewer_employee_id, reviewer.full_name AS reviewer_name
        FROM users u
        LEFT JOIN users reviewer ON reviewer.id = u.reviewed_by
        WHERE u.approval_status = ?
    """
    params: list[object] = [normalized_status]

    if not include_admin:
        query += " AND u.role != ?"
        params.append(ROLE_ADMIN)

    query += " ORDER BY u.created_at ASC"

    with _connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [_serialize_user_row(row) for row in rows]


def list_review_history(limit: int = 100, include_admin: bool = False) -> list[dict]:
    safe_limit = max(1, min(limit, 500))

    query = """
        SELECT u.*, reviewer.employee_id AS reviewer_employee_id, reviewer.full_name AS reviewer_name
        FROM users u
        LEFT JOIN users reviewer ON reviewer.id = u.reviewed_by
        WHERE u.approval_status IN (?, ?)
    """
    params: list[object] = [APPROVAL_APPROVED, APPROVAL_REJECTED]

    if not include_admin:
        query += " AND u.role != ?"
        params.append(ROLE_ADMIN)

    query += " ORDER BY COALESCE(u.reviewed_at, u.created_at) DESC LIMIT ?"
    params.append(safe_limit)

    with _connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [_serialize_user_row(row) for row in rows]


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

    with _connection() as conn:
        target = conn.execute(
            "SELECT id, role FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if target is None:
            raise LookupError("User not found.")

        reviewer = conn.execute(
            "SELECT id, role FROM users WHERE id = ?",
            (reviewed_by,),
        ).fetchone()
        if reviewer is None:
            raise LookupError("Reviewer not found.")
        if str(reviewer["role"] or ROLE_USER) != ROLE_ADMIN:
            raise PermissionError("Only admins can review user accounts.")

        if str(target["role"] or ROLE_USER) == ROLE_ADMIN:
            raise PermissionError("Admin account status cannot be modified.")

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


def set_user_approval_status(
    employee_id: str,
    approval_status: str,
    reviewed_by: Optional[int] = None,
    review_reason: Optional[str] = None,
) -> bool:
    normalized_status = _validate_approval_status(approval_status)
    cleaned_employee_id = employee_id.strip()
    normalized_reason = _normalize_review_reason(review_reason)

    with _connection() as conn:
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

    with _connection() as conn:
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
    with _connection() as conn:
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
    with _connection() as conn:
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

    with _connection() as conn:
        cursor = conn.execute(
            f"UPDATE ingestion_jobs SET {assignments} WHERE job_id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0


def create_conversation(user_id: int, title: str = "New Chat") -> int:
    now = _utc_now_iso()
    with _connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO conversations (user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, title, now, now),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_conversations(user_id: int) -> list[dict]:
    with _connection() as conn:
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


def add_message(
    conversation_id: int,
    user_id: int,
    role: str,
    content: str,
    sources: Optional[list[dict]] = None,
) -> None:
    if role not in ("user", "assistant"):
        raise ValueError("Invalid message role.")

    with _connection() as conn:
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


def get_messages(conversation_id: int, user_id: int) -> list[dict]:
    with _connection() as conn:
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


def ensure_user_has_conversation(user_id: int) -> int:
    conversations = list_conversations(user_id)
    if conversations:
        return int(conversations[0]["id"])
    return create_conversation(user_id=user_id, title="New Chat")


def rename_conversation(conversation_id: int, user_id: int, new_title: str) -> str:
    cleaned_title = " ".join((new_title or "").split()).strip()
    if not cleaned_title:
        raise ValueError("Chat title cannot be empty.")

    cleaned_title = cleaned_title[:80]

    with _connection() as conn:
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


def delete_conversation(conversation_id: int, user_id: int) -> None:
    with _connection() as conn:
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

    validation_error = _validate_registration(admin_employee_id, admin_name, admin_password)
    if validation_error:
        return AuthResult(success=False, message=f"Admin bootstrap failed: {validation_error}")

    with _connection() as conn:
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
