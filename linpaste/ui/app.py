"""Single-instance Adwaita application that hosts the popup window.

Using a unique application id means a second ``linpaste show`` (e.g. pressing
Super+V again) re-activates the running instance and raises its window instead
of spawning a duplicate.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio  # noqa: E402

from .. import config  # noqa: E402
from .window import LinPasteWindow  # noqa: E402


class LinPasteApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=config.APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self) -> None:
        win = self.get_active_window()
        if win is None:
            win = LinPasteWindow(self)
        win.present()


def run() -> int:
    app = LinPasteApp()
    return app.run([])
