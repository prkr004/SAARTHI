"""Phase 5 micro-profiling for practical bottlenecks.

This script benchmarks two hotspots that directly impact API responsiveness:
1) Conversation list SQL query under larger message volume.
2) Source formatting overhead for repeated source metadata.
"""

from __future__ import annotations

import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from query import format_source_label


def _measure_ms(fn, iterations: int = 12) -> dict[str, float]:
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        elapsed_ms = (time.perf_counter() - start) * 1000
        samples.append(elapsed_ms)
    return {
        "avg_ms": round(statistics.mean(samples), 2),
        "median_ms": round(statistics.median(samples), 2),
        "p95_ms": round(sorted(samples)[max(0, int(iterations * 0.95) - 1)], 2),
        "min_ms": round(min(samples), 2),
        "max_ms": round(max(samples), 2),
    }


def _seed_sqlite(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")

    conn.execute(
        """
        CREATE TABLE users (
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
        CREATE TABLE conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sources_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        INSERT INTO users (employee_id, full_name, password_hash, created_at)
        VALUES ('EMPB001', 'Benchmark User', 'hash', '2026-04-07T00:00:00+00:00')
        """
    )
    user_id = 1

    now = "2026-04-07T00:00:00+00:00"
    total_conversations = 4000
    conversations = [(user_id, f"Conversation {idx}", now, now) for idx in range(1, total_conversations + 1)]
    conn.executemany(
        """
        INSERT INTO conversations (user_id, title, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        conversations,
    )

    message_rows = []
    for conversation_id in range(1, total_conversations + 1):
        for msg_idx in range(20):
            role = "user" if msg_idx % 2 == 0 else "assistant"
            message_rows.append((conversation_id, role, f"message {msg_idx}", "[]", now))

    conn.executemany(
        """
        INSERT INTO messages (conversation_id, role, content, sources_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        message_rows,
    )
    conn.commit()
    return conn


def benchmark_conversation_query() -> dict[str, dict[str, float]]:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "profile.db"
        conn = _seed_sqlite(db_path)

        baseline_join_sql = """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            WHERE c.user_id = ?
            GROUP BY c.id
            ORDER BY c.updated_at DESC
        """

        optimized_sql = """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (
                       SELECT COUNT(1)
                       FROM messages m
                       WHERE m.conversation_id = c.id
                   ) AS message_count
            FROM conversations c
            WHERE c.user_id = ?
            ORDER BY c.updated_at DESC
        """

        conn.execute("CREATE INDEX idx_users_employee_id ON users(employee_id)")
        conn.execute("CREATE INDEX idx_conversations_user_updated ON conversations(user_id, updated_at DESC)")
        conn.execute("CREATE INDEX idx_messages_conversation_id_id ON messages(conversation_id, id)")
        conn.execute("CREATE INDEX idx_messages_conversation_role ON messages(conversation_id, role)")
        conn.commit()

        def run_query(sql: str):
            rows = conn.execute(sql, (1,)).fetchall()
            if len(rows) != 4000:
                raise RuntimeError("Unexpected row count during benchmark")

        def run_baseline_join():
            run_query(baseline_join_sql)

        def run_optimized():
            run_query(optimized_sql)

        run_baseline_join()
        baseline_join = _measure_ms(run_baseline_join)

        run_optimized()
        optimized = _measure_ms(run_optimized)
        conn.close()

    return {"baseline_join": baseline_join, "optimized_query": optimized}


def benchmark_source_formatting() -> dict[str, dict[str, float]]:
    sources = []
    for i in range(2500):
        sources.append(
            {
                "content": f"snippet-{i}",
                "metadata": {
                    "source": "RBI_Master_Direction_2025.pdf" if i % 2 == 0 else "RBI_Master_Direction_2024.pdf",
                    "page": (i % 18) + 1,
                },
            }
        )

    def naive():
        out = []
        for src in sources:
            metadata = src["metadata"]
            doc_name, doc_link, page = format_source_label(metadata)
            out.append((doc_name, doc_link, page))
        return out

    def cached():
        out = []
        cache: dict[tuple[str | None, int | None], tuple[str, str | None, int | None]] = {}
        for src in sources:
            metadata = src["metadata"]
            source_key = metadata.get("source")
            page_key = metadata.get("page")
            key = (str(source_key) if source_key is not None else None, int(page_key) if isinstance(page_key, int) else None)
            value = cache.get(key)
            if value is None:
                value = format_source_label(metadata)
                cache[key] = value
            out.append(value)
        return out

    return {
        "naive": _measure_ms(naive),
        "cached": _measure_ms(cached),
    }


def _percent_delta(old: float, new: float) -> float:
    if old <= 0:
        return 0.0
    return round(((old - new) / old) * 100, 2)


def main() -> None:
    print("Phase 5 profiling run")
    print("-" * 80)

    conversation = benchmark_conversation_query()
    source_formatting = benchmark_source_formatting()

    print("Conversation query benchmark")
    print(conversation)
    print(
        "improvement(median_ms):",
        f"{_percent_delta(conversation['baseline_join']['median_ms'], conversation['optimized_query']['median_ms'])}%",
    )
    print()

    print("Source formatting benchmark")
    print(source_formatting)
    print(
        "improvement(median_ms):",
        f"{_percent_delta(source_formatting['naive']['median_ms'], source_formatting['cached']['median_ms'])}%",
    )


if __name__ == "__main__":
    main()
