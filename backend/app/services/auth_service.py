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
    db_path = chat_store.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def initialize_session_store() -> None:
    """Create API session table if absent."""

    with _connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                user_agent TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_api_sessions_user_id
            ON api_sessions(user_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_api_sessions_expires_at
            ON api_sessions(expires_at)
            """
        )
        conn.commit()


def create_session(user_id: int, user_agent: Optional[str] = None) -> tuple[str, datetime]:
    """Create an opaque bearer token and persist hashed value in SQLite."""

    settings = get_settings()
    token = secrets.token_urlsafe(settings.session_token_bytes)
    expires_at = _utc_now() + timedelta(minutes=settings.access_token_ttl_minutes)

    with _connection() as conn:
        conn.execute(
            """
            INSERT INTO api_sessions (token_hash, user_id, created_at, expires_at, user_agent)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                _hash_token(token),
                user_id,
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
        row = conn.execute(
            """
            SELECT u.id AS user_id, u.employee_id, u.full_name, s.expires_at
            FROM api_sessions s
            INNER JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
              AND s.revoked_at IS NULL
              AND s.expires_at > ?
            """,
            (token_hash, now_iso),
        ).fetchone()

        if row is None:
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

        return {
            "user_id": int(row["user_id"]),
            "employee_id": row["employee_id"],
            "full_name": row["full_name"],
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
