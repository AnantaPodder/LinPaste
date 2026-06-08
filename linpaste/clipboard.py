"""Thin wrappers around the ``wl-clipboard`` CLI (wl-copy / wl-paste).

Every interaction with the Wayland clipboard goes through here so the rest of
the codebase never shells out directly.
"""

import subprocess

# Mime-type hints that password managers / sensitive sources advertise. When the
# clipboard offers any of these we skip storing the content.
SENSITIVE_TYPES = {
    "x-kde-passwordManagerHint",
    "application/x-secret",
}


def copy(text: str) -> None:
    """Put ``text`` onto the Wayland clipboard."""
    subprocess.run(
        ["wl-copy", "--type", "text/plain;charset=utf-8"],
        input=text.encode("utf-8"),
        check=False,
    )


def paste_into_active() -> bool:
    """Ask the LinPaste GNOME Shell extension to synthesize Ctrl+V.

    Input injection is impossible from this sandboxed process on Wayland, so we
    delegate to the capture extension (which runs inside gnome-shell and exports
    a ``Paste`` method). Call this *after* the popup window has closed, so focus
    has returned to the target window. Returns False if the call can't be made
    (extension not running, not a GNOME session, …) — the copy still stands.
    """
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            "org.gnome.Shell",
            "/io/github/anantapodder/LinPaste",
            "io.github.anantapodder.LinPaste",
            "Paste",
            None,
            None,
            Gio.DBusCallFlags.NONE,
            1000,
            None,
        )
        return True
    except GLib.Error:
        return False


def list_types() -> list[str]:
    """Return the mime types currently offered by the clipboard (best-effort)."""
    try:
        out = subprocess.run(
            ["wl-paste", "--list-types"],
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in out.stdout.decode("utf-8", "replace").splitlines() if line.strip()]


def is_sensitive() -> bool:
    """True if the current clipboard looks like it came from a password manager."""
    types = set(list_types())
    return bool(types & SENSITIVE_TYPES)
