"""Session-backed auth helpers for API endpoints."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

import chat_store

from backend.app.core.config import get_settings


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _connection() -> sqlite3.Connection:
    db_path = chat_store.get_session_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_user_scope(user_scope: str) -> str:
    normalized = str(user_scope or "").strip().lower()
    if normalized not in {chat_store.USER_SCOPE_EMPLOYEE, chat_store.USER_SCOPE_ADMIN}:
        raise ValueError("Invalid user scope.")
    return normalized


def initialize_session_store() -> None:
    """Create API session table if absent."""

    with _connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                user_scope TEXT NOT NULL DEFAULT 'employee',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                user_agent TEXT
            )
            """
        )
        columns = {
            str(item["name"]).lower()
            for item in conn.execute("PRAGMA table_info(api_sessions)").fetchall()
        }
        if "user_scope" not in columns:
            conn.execute(
                "ALTER TABLE api_sessions ADD COLUMN user_scope TEXT NOT NULL DEFAULT 'employee'"
            )

        conn.execute(
            """
            UPDATE api_sessions
            SET user_scope = 'employee'
            WHERE user_scope IS NULL OR TRIM(user_scope) = ''
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_api_sessions_scope_user_id
            ON api_sessions(user_scope, user_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_api_sessions_expires_at
            ON api_sessions(expires_at)
            """
        )
        conn.commit()


def create_session(
    user_id: int,
    user_scope: str,
    user_agent: Optional[str] = None,
) -> tuple[str, datetime]:
    """Create an opaque bearer token and persist hashed value in SQLite."""

    settings = get_settings()
    token = secrets.token_urlsafe(settings.session_token_bytes)
    expires_at = _utc_now() + timedelta(minutes=settings.access_token_ttl_minutes)
    normalized_scope = _normalize_user_scope(user_scope)

    with _connection() as conn:
        conn.execute(
            """
            INSERT INTO api_sessions (token_hash, user_id, user_scope, created_at, expires_at, user_agent)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _hash_token(token),
                user_id,
                normalized_scope,
                _utc_now_iso(),
                expires_at.isoformat(),
                (user_agent or "")[:255],
            ),
        )

        # Cap active sessions per user to reduce token sprawl risk.
        now_iso = _utc_now_iso()
        conn.execute(
            """
            WITH stale AS (
                SELECT token_hash
                FROM api_sessions
                WHERE user_id = ?
                                    AND user_scope = ?
                  AND revoked_at IS NULL
                  AND expires_at > ?
                ORDER BY created_at DESC
                LIMIT -1 OFFSET ?
            )
            UPDATE api_sessions
            SET revoked_at = ?
            WHERE token_hash IN (SELECT token_hash FROM stale)
            """,
            (
                user_id,
                normalized_scope,
                now_iso,
                settings.session_max_active_per_user,
                now_iso,
            ),
        )
        conn.commit()

    return token, expires_at


def get_session_user(token: str) -> Optional[dict]:
    """Resolve a valid non-expired session token to a user profile."""

    token_hash = _hash_token(token)
    now_iso = _utc_now_iso()

    with _connection() as conn:
        session_row = conn.execute(
            """
            SELECT user_id, user_scope
            FROM api_sessions
            WHERE token_hash = ?
              AND revoked_at IS NULL
              AND expires_at > ?
            """,
            (token_hash, now_iso),
        ).fetchone()

        if session_row is None:
            conn.execute(
                """
                UPDATE api_sessions
                SET revoked_at = ?
                WHERE token_hash = ?
                  AND revoked_at IS NULL
                  AND expires_at <= ?
                """,
                (now_iso, token_hash, now_iso),
            )
            conn.commit()
            return None

    user_scope = _normalize_user_scope(str(session_row["user_scope"]))
    user = chat_store.get_user_by_id(int(session_row["user_id"]), scope=user_scope)
    if user is None:
        revoke_session(token)
        return None

    return {
        "user_id": int(user["id"]),
        "employee_id": user["employee_id"],
        "full_name": user["full_name"],
        "role": user["role"],
        "approval_status": user["approval_status"],
        "email": user.get("email"),
    }


def revoke_session(token: str) -> bool:
    """Revoke a session token. Returns True if revocation was applied."""

    token_hash = _hash_token(token)
    with _connection() as conn:
        cursor = conn.execute(
            """
            UPDATE api_sessions
            SET revoked_at = ?
            WHERE token_hash = ? AND revoked_at IS NULL
            """,
            (_utc_now_iso(), token_hash),
        )
        conn.commit()
        return cursor.rowcount > 0


def purge_expired_sessions() -> int:
    """Delete old revoked sessions to keep DB lean."""

    now_iso = _utc_now_iso()
    with _connection() as conn:
        cursor = conn.execute(
            """
            DELETE FROM api_sessions
                        WHERE expires_at <= ?
            """,
            (now_iso,),
        )
        conn.commit()
        return cursor.rowcount
