"""Command-line entry point and subcommand dispatch.

Subcommands:
  store   read clipboard text from stdin and save it (invoked by wl-paste --watch)
  show    open the GTK popup
  list    print recent history to stdout
  clear   wipe history (keeps pinned unless --all)
  status  show whether the capture extension is installed/enabled
"""

import argparse
import sys

from . import __version__, clipboard, config, db


def cmd_store(args: argparse.Namespace) -> int:
    """Persist clipboard content piped on stdin. Spawned once per copy.

    Text by default; pass ``--image --mime <type>`` to store raw image bytes.
    """
    # Respect password managers: skip anything flagged sensitive.
    if not args.force and clipboard.is_sensitive():
        return 0
    raw = sys.stdin.buffer.read()
    if args.image:
        if db.add_image(raw, mime=args.mime) is not None:
            db.trim()
        return 0
    text = raw.decode("utf-8", "replace")
    if db.add_entry(text) is not None:
        db.trim()
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    entries = db.list_entries(limit=args.limit, query=args.query)
    for e in entries:
        marker = "*" if e.pinned else " "
        preview = e.content.replace("\n", "⏎")  # ⏎ for newlines
        if len(preview) > 80:
            preview = preview[:77] + "..."
        print(f"{marker} [{e.id}] {preview}")
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    removed = db.clear(keep_pinned=not args.all)
    print(f"Removed {removed} entr{'y' if removed == 1 else 'ies'}.")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    # Imported lazily so the lightweight `store` path never loads GTK.
    from .ui.app import run as run_ui

    return run_ui()


EXT_UUID = "linpaste-capture@anantapodder.github.io"


def cmd_enable(args: argparse.Namespace) -> int:
    """Enable the capture extension in the running GNOME session."""
    import shutil
    import subprocess

    if shutil.which("gnome-extensions") is None:
        print("gnome-extensions tool not found — is this a GNOME session?")
        return 1
    out = subprocess.run(
        ["gnome-extensions", "enable", EXT_UUID],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        msg = (out.stderr or out.stdout).strip()
        print(f"Could not enable capture extension: {msg}")
        print("If you just installed it, log out and back in once, then retry.")
        return 1
    return cmd_status(args)


HOTKEY = "<Super>v"
HOTKEY_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/linpaste/"


def _linpaste_command() -> str:
    """Absolute path to the installed `linpaste` launcher (for the hotkey)."""
    import shutil

    return shutil.which("linpaste") or "linpaste"


def cmd_setup(args: argparse.Namespace) -> int:
    """Bind the Super+V hotkey and enable the capture extension (per-user)."""
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio

    schema = "org.gnome.settings-daemon.plugins.media-keys"
    base = Gio.Settings.new(schema)
    paths = list(base.get_strv("custom-keybindings"))
    if HOTKEY_PATH not in paths:
        paths.append(HOTKEY_PATH)
        base.set_strv("custom-keybindings", paths)

    custom = Gio.Settings.new_with_path(schema + ".custom-keybinding", HOTKEY_PATH)
    custom.set_string("name", "LinPaste")
    custom.set_string("command", f"{_linpaste_command()} show")
    custom.set_string("binding", HOTKEY)
    Gio.Settings.sync()
    print(f"Bound {HOTKEY} -> linpaste show")

    # Enabling the extension only succeeds once the shell has scanned it.
    print("Enabling capture extension…")
    return cmd_enable(args)


def cmd_status(args: argparse.Namespace) -> int:
    """Report whether the GNOME Shell capture extension is active."""
    import os
    import shutil
    import subprocess

    uuid = EXT_UUID
    # Installed per-user (pip/install.sh) or system-wide (.deb).
    on_disk = any(
        os.path.isfile(p)
        for p in (
            os.path.expanduser(
                f"~/.local/share/gnome-shell/extensions/{uuid}/extension.js"
            ),
            f"/usr/share/gnome-shell/extensions/{uuid}/extension.js",
        )
    )

    if shutil.which("gnome-extensions") is None:
        print("gnome-extensions tool not found — is this a GNOME session?")
        return 1

    out = subprocess.run(
        ["gnome-extensions", "info", uuid],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        # The running shell doesn't know the extension yet.
        if on_disk:
            print("Capture extension is installed on disk but NOT yet loaded.")
            print("Log out and back in once so GNOME loads it, then run:")
            print("    linpaste enable")
            return 1
        print(f"Capture extension '{uuid}' is NOT installed.")
        print("Run ./install.sh (then log out/in) to enable clipboard capture.")
        return 1

    print(out.stdout.strip())
    if "State: ACTIVE" in out.stdout:
        print("\nCapture is ACTIVE — copies are being recorded.")
    elif "Enabled: No" in out.stdout:
        print("\nExtension is loaded but NOT enabled. Turn it on with:")
        print("    linpaste enable")
    else:
        print("\nExtension loaded but not ACTIVE yet — try: linpaste enable")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="linpaste", description="Clipboard history for Wayland/GNOME.")
    p.add_argument("--version", action="version", version=f"linpaste {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("store", help="store clipboard content from stdin")
    sp.add_argument("--force", action="store_true", help="store even if flagged sensitive")
    sp.add_argument("--image", action="store_true", help="treat stdin as raw image bytes")
    sp.add_argument("--mime", default="image/png", help="MIME type of --image data")
    sp.set_defaults(func=cmd_store)

    sp = sub.add_parser("show", help="open the clipboard popup")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("list", help="print recent history")
    sp.add_argument("-n", "--limit", type=int, default=config.SHOW_LIMIT)
    sp.add_argument("-q", "--query", default=None, help="filter substring")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("clear", help="wipe history")
    sp.add_argument("--all", action="store_true", help="also remove pinned entries")
    sp.set_defaults(func=cmd_clear)

    sp = sub.add_parser("status", help="show capture-extension status")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("enable", help="enable the capture extension")
    sp.set_defaults(func=cmd_enable)

    sp = sub.add_parser("setup", help="bind Super+V and enable capture (per-user)")
    sp.set_defaults(func=cmd_setup)

    return p


def main(argv: list[str] | None = None) -> int:
    db.init_db()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
