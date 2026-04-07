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

DEFAULT_ADMIN_EMPLOYEE_ID = "ADMIN001"
DEFAULT_ADMIN_NAME = "Bank Admin"
DEFAULT_ADMIN_PASSWORD = "AdminPass#2026"


@dataclass
class AuthResult:
    success: bool
    message: str
    user_id: Optional[int] = None
    employee_id: Optional[str] = None
    full_name: Optional[str] = None


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


def initialize_db() -> None:
    with _connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
            """
        )

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


def register_user(employee_id: str, full_name: str, password: str) -> AuthResult:
    employee_id = employee_id.strip()
    full_name = full_name.strip()

    validation_error = _validate_registration(employee_id, full_name, password)
    if validation_error:
        return AuthResult(success=False, message=validation_error)

    with _connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO users (employee_id, full_name, password_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (employee_id, full_name, _hash_password(password), _utc_now_iso()),
            )
            conn.commit()
            return AuthResult(success=True, message="Registration successful. Please login.")
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
        )


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
                   COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            WHERE c.user_id = ?
            GROUP BY c.id
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
                INSERT INTO users (employee_id, full_name, password_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (admin_employee_id, admin_name, _hash_password(admin_password), _utc_now_iso()),
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
                    failed_attempts = 0,
                    locked_until = NULL
                WHERE id = ?
                """,
                (admin_name, _hash_password(admin_password), row["id"]),
            )
            conn.commit()
            return AuthResult(success=True, message="Admin account updated from environment variables.")

        conn.execute(
            "UPDATE users SET full_name = ? WHERE id = ?",
            (admin_name, row["id"]),
        )
        conn.commit()
        return AuthResult(success=True, message="Admin account already configured.")
