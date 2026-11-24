"""SQLite session storage (stdlib sqlite3; calls are wrapped in threads by the routes)."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,   -- 'user' or 'assistant'
    content     TEXT NOT NULL,
    metadata    TEXT,            -- JSON string, assistant messages only
    created_at  TEXT NOT NULL    -- server time, ISO-8601
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, id);
CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,
    system_prompt TEXT,
    created_at    TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(path: str) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(path: str) -> None:
    """Create the parent dir and the schema (idempotent, runs on every startup)."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.commit()


def ping(path: str) -> bool:
    try:
        with connect(path) as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False


def get_history(path: str, session_id: str) -> list[dict[str, Any]]:
    """Messages oldest first. Assistant rows carry their parsed metadata."""
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        item: dict[str, Any] = {"role": r["role"], "content": r["content"]}
        if r["metadata"]:
            item["metadata"] = json.loads(r["metadata"])
        out.append(item)
    return out


def get_session_prompt(path: str, session_id: str) -> str | None:
    with connect(path) as conn:
        row = conn.execute(
            "SELECT system_prompt FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    return row["system_prompt"] if row else None


def save_exchange(
    path: str,
    session_id: str,
    user_content: str,
    assistant_content: str,
    metadata: dict[str, Any],
    system_prompt: str | None,
) -> None:
    """Persist user + assistant rows (and the session prompt) in ONE transaction."""
    now = _now()
    with connect(path) as conn:
        with conn:  # commit on success, roll back on error
            conn.execute(
                "INSERT INTO sessions (session_id, system_prompt, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "system_prompt = COALESCE(excluded.system_prompt, sessions.system_prompt)",
                (session_id, system_prompt, now),
            )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, metadata, created_at) "
                "VALUES (?, 'user', ?, NULL, ?)",
                (session_id, user_content, now),
            )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, metadata, created_at) "
                "VALUES (?, 'assistant', ?, ?, ?)",
                (session_id, assistant_content, json.dumps(metadata), _now()),
            )
