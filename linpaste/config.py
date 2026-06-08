"""Paths and tunable settings for LinPaste.

All filesystem locations follow the XDG Base Directory spec so the tool behaves
predictably on a standard Ubuntu/GNOME setup.
"""

import os
from pathlib import Path

APP_ID = "io.github.anantapodder.LinPaste"

# Maximum number of *unpinned* entries to keep. Pinned entries are never trimmed.
MAX_HISTORY = int(os.environ.get("LINPASTE_MAX_HISTORY", "500"))

# Number of entries shown in the popup at once.
SHOW_LIMIT = int(os.environ.get("LINPASTE_SHOW_LIMIT", "200"))


def _xdg_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def data_dir() -> Path:
    """Directory holding LinPaste's persistent state (created on demand)."""
    d = _xdg_data_home() / "linpaste"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    """Path to the SQLite history database."""
    return data_dir() / "history.db"
