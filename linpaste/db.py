"""SQLite storage layer — the only module that touches the database.

The schema keeps one row per distinct clipboard text. Re-copying something that
already exists doesn't create a duplicate; it bumps the existing row to the top
via ``last_used_at`` (see :func:`add_entry`).
"""

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id           INTEGER PRIMARY KEY,
    content      TEXT NOT NULL,
    html         TEXT,
    hash         TEXT NOT NULL UNIQUE,
    pinned       INTEGER NOT NULL DEFAULT 0,
    created_at   REAL NOT NULL,
    last_used_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entries_order
    ON entries (pinned DESC, last_used_at DESC);
"""


@dataclass
class Entry:
    id: int
    content: str
    html: Optional[str]
    pinned: bool
    created_at: float
    last_used_at: float


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create the schema if it doesn't exist yet."""
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def add_entry(content: str, html: Optional[str] = None) -> Optional[int]:
    """Insert a new clipboard entry, or bump an existing identical one.

    Returns the row id, or ``None`` if the content was empty/whitespace-only.
    """
    if not content or not content.strip():
        return None

    h = _hash(content)
    now = time.time()
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        row = conn.execute("SELECT id FROM entries WHERE hash = ?", (h,)).fetchone()
        if row is not None:
            # Already seen — move it back to the top instead of duplicating.
            conn.execute(
                "UPDATE entries SET last_used_at = ?, html = COALESCE(?, html) "
                "WHERE id = ?",
                (now, html, row["id"]),
            )
            return row["id"]
        cur = conn.execute(
            "INSERT INTO entries (content, html, hash, pinned, created_at, last_used_at) "
            "VALUES (?, ?, ?, 0, ?, ?)",
            (content, html, h, now, now),
        )
        return cur.lastrowid


def list_entries(limit: int = config.SHOW_LIMIT, query: Optional[str] = None) -> list[Entry]:
    """Return entries, pinned first then most-recently-used, optionally filtered."""
    sql = "SELECT * FROM entries"
    params: list = []
    if query:
        sql += " WHERE content LIKE ?"
        params.append(f"%{query}%")
    sql += " ORDER BY pinned DESC, last_used_at DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        rows = conn.execute(sql, params).fetchall()
    return [
        Entry(
            id=r["id"],
            content=r["content"],
            html=r["html"],
            pinned=bool(r["pinned"]),
            created_at=r["created_at"],
            last_used_at=r["last_used_at"],
        )
        for r in rows
    ]


def touch(entry_id: int) -> None:
    """Bump an entry to the top (used when the user re-selects it)."""
    with _connect() as conn:
        conn.execute(
            "UPDATE entries SET last_used_at = ? WHERE id = ?",
            (time.time(), entry_id),
        )


def set_pinned(entry_id: int, pinned: bool) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE entries SET pinned = ? WHERE id = ?",
            (1 if pinned else 0, entry_id),
        )


def delete(entry_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))


def clear(keep_pinned: bool = True) -> int:
    """Delete history. Returns the number of rows removed."""
    with _connect() as conn:
        sql = "DELETE FROM entries"
        if keep_pinned:
            sql += " WHERE pinned = 0"
        cur = conn.execute(sql)
        return cur.rowcount


def trim(max_items: int = config.MAX_HISTORY) -> int:
    """Keep at most ``max_items`` unpinned entries; drop the oldest overflow."""
    with _connect() as conn:
        cur = conn.execute(
            """
            DELETE FROM entries
            WHERE pinned = 0 AND id NOT IN (
                SELECT id FROM entries WHERE pinned = 0
                ORDER BY last_used_at DESC LIMIT ?
            )
            """,
            (max_items,),
        )
        return cur.rowcount
