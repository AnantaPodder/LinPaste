"""SQLite storage layer — the only module that touches the database.

The schema keeps one row per distinct clipboard text. Re-copying something that
already exists doesn't create a duplicate — the existing row is left in place
(see :func:`add_entry`). History is ordered by ``created_at`` (insertion order),
so reusing or re-copying an old entry never reshuffles the list; only genuinely
new content appears at the top.
"""

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id           INTEGER PRIMARY KEY,
    content      TEXT NOT NULL,
    html         TEXT,
    hash         TEXT NOT NULL UNIQUE,
    kind         TEXT NOT NULL DEFAULT 'text',
    pinned       INTEGER NOT NULL DEFAULT 0,
    created_at   REAL NOT NULL,
    last_used_at REAL NOT NULL
);
"""


@dataclass
class Entry:
    id: int
    content: str  # text body, or absolute file path for image entries
    html: Optional[str]
    pinned: bool
    created_at: float
    last_used_at: float
    kind: str = "text"  # "text" | "image"


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash(content: str) -> str:
    return _hash_bytes(content.encode("utf-8"))


def _ensure_kind_column(conn: sqlite3.Connection) -> None:
    """Add the ``kind`` column to databases created before image support."""
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(entries)").fetchall()]
    if cols and "kind" not in cols:
        conn.execute("ALTER TABLE entries ADD COLUMN kind TEXT NOT NULL DEFAULT 'text'")


def _ensure_order_index(conn: sqlite3.Connection) -> None:
    """Index history by insertion order; drop any older last_used_at index.

    Early versions ordered by ``last_used_at``; the same index name now covers
    ``created_at``, so an existing database needs its stale index rebuilt.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_entries_order'"
    ).fetchone()
    if row is not None and row["sql"] and "last_used_at" in row["sql"]:
        conn.execute("DROP INDEX idx_entries_order")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entries_order "
        "ON entries (pinned DESC, created_at DESC)"
    )


def _prepare(conn: sqlite3.Connection) -> None:
    """Ensure the schema, columns, and indexes exist before a query runs."""
    conn.executescript(_SCHEMA)
    _ensure_kind_column(conn)
    _ensure_order_index(conn)


def _images_dir() -> Path:
    d = config.data_dir() / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _unlink_image(path: Optional[str]) -> None:
    """Best-effort removal of an image file backing a deleted entry."""
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create the schema if it doesn't exist yet."""
    with _connect() as conn:
        _prepare(conn)


def add_entry(content: str, html: Optional[str] = None) -> Optional[int]:
    """Insert a new clipboard entry, or refresh an existing identical one.

    Returns the row id, or ``None`` if the content was empty/whitespace-only.
    """
    if not content or not content.strip():
        return None

    h = _hash(content)
    now = time.time()
    with _connect() as conn:
        _prepare(conn)
        row = conn.execute("SELECT id FROM entries WHERE hash = ?", (h,)).fetchone()
        if row is not None:
            # Already seen — keep its position (ordering is by created_at), just
            # refresh last_used_at and pick up any newly captured HTML.
            conn.execute(
                "UPDATE entries SET last_used_at = ?, html = COALESCE(?, html) "
                "WHERE id = ?",
                (now, html, row["id"]),
            )
            return row["id"]
        cur = conn.execute(
            "INSERT INTO entries (content, html, hash, kind, pinned, created_at, last_used_at) "
            "VALUES (?, ?, ?, 'text', 0, ?, ?)",
            (content, html, h, now, now),
        )
        return cur.lastrowid


def add_image(data: bytes, mime: str = "image/png") -> Optional[int]:
    """Store raw image bytes as a file and record a row pointing at it.

    Dedups by content hash (re-copying the same image just bumps it back to the
    top). Returns the row id, or ``None`` if ``data`` is empty.
    """
    if not data:
        return None

    h = _hash_bytes(data)
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
           "image/bmp": "bmp", "image/gif": "gif", "image/webp": "webp"}.get(mime, "png")
    path = _images_dir() / f"{h}.{ext}"
    if not path.exists():
        path.write_bytes(data)

    now = time.time()
    with _connect() as conn:
        _prepare(conn)
        row = conn.execute("SELECT id FROM entries WHERE hash = ?", (h,)).fetchone()
        if row is not None:
            # Keep its position; just note it was used again.
            conn.execute("UPDATE entries SET last_used_at = ? WHERE id = ?", (now, row["id"]))
            return row["id"]
        cur = conn.execute(
            "INSERT INTO entries (content, html, hash, kind, pinned, created_at, last_used_at) "
            "VALUES (?, NULL, ?, 'image', 0, ?, ?)",
            (str(path), h, now, now),
        )
        return cur.lastrowid


def list_entries(limit: int = config.SHOW_LIMIT, query: Optional[str] = None) -> list[Entry]:
    """Return entries, pinned first then newest-copied-first, optionally filtered."""
    sql = "SELECT * FROM entries"
    params: list = []
    if query:
        # Only text entries are searchable; an image's stored value is a file
        # path, which would otherwise match queries like "png" or "images".
        sql += " WHERE kind = 'text' AND content LIKE ?"
        params.append(f"%{query}%")
    # Order by insertion time so reusing an entry never changes its position.
    # ``id`` breaks ties for a stable order when timestamps collide.
    sql += " ORDER BY pinned DESC, created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        _prepare(conn)
        rows = conn.execute(sql, params).fetchall()
    return [
        Entry(
            id=r["id"],
            content=r["content"],
            html=r["html"],
            pinned=bool(r["pinned"]),
            created_at=r["created_at"],
            last_used_at=r["last_used_at"],
            kind=r["kind"] if "kind" in r.keys() else "text",
        )
        for r in rows
    ]


def set_pinned(entry_id: int, pinned: bool) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE entries SET pinned = ? WHERE id = ?",
            (1 if pinned else 0, entry_id),
        )


def delete(entry_id: int) -> None:
    with _connect() as conn:
        _ensure_kind_column(conn)
        row = conn.execute(
            "SELECT content, kind FROM entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if row is not None and row["kind"] == "image":
            _unlink_image(row["content"])
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))


def clear(keep_pinned: bool = True) -> int:
    """Delete history. Returns the number of rows removed."""
    with _connect() as conn:
        _ensure_kind_column(conn)
        sel = "SELECT content FROM entries WHERE kind = 'image'"
        if keep_pinned:
            sel += " AND pinned = 0"
        for r in conn.execute(sel).fetchall():
            _unlink_image(r["content"])
        sql = "DELETE FROM entries"
        if keep_pinned:
            sql += " WHERE pinned = 0"
        cur = conn.execute(sql)
        return cur.rowcount


def trim(max_items: int = config.MAX_HISTORY) -> int:
    """Keep at most ``max_items`` unpinned entries; drop the oldest overflow."""
    keep = """
        SELECT id FROM entries WHERE pinned = 0
        ORDER BY created_at DESC LIMIT ?
    """
    with _connect() as conn:
        _ensure_kind_column(conn)
        for r in conn.execute(
            f"SELECT content FROM entries "
            f"WHERE pinned = 0 AND kind = 'image' AND id NOT IN ({keep})",
            (max_items,),
        ).fetchall():
            _unlink_image(r["content"])
        cur = conn.execute(
            f"DELETE FROM entries WHERE pinned = 0 AND id NOT IN ({keep})",
            (max_items,),
        )
        return cur.rowcount
