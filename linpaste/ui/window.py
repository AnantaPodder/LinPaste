"""The clipboard popup window.

A search entry on top of a scrollable list of history rows. Pinned items sort
first, then most-recently-used. Keyboard-first, Win+V style:

  - type to filter
  - Up/Down to move through results (works while focus is in the search box)
  - Enter copies the selected entry, closes, and pastes it into the window
    that had focus (set LINPASTE_AUTO_PASTE=0 to only copy)
  - Delete removes the selected entry
  - Ctrl+P toggles a pin on the selected entry
  - Esc closes

Entries may be text or images; image entries show a thumbnail and copy the
image back to the clipboard on Enter. The trash button in the header clears all
history (pinned included).
"""

import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from .. import clipboard, config, db  # noqa: E402


def _relative_time(ts: float) -> str:
    delta = datetime.datetime.now().timestamp() - ts
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"


class LinPasteWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app)
        self.set_title("LinPaste")
        self.set_default_size(460, 540)

        self._entries: list[db.Entry] = []

        # --- layout -------------------------------------------------------
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar(show_end_title_buttons=False)
        title = Adw.WindowTitle(title="LinPaste", subtitle="Clipboard history")
        header.set_title_widget(title)

        clear_all = Gtk.Button(icon_name="user-trash-symbolic")
        clear_all.set_tooltip_text("Clear clipboard history (keeps pinned)")
        clear_all.add_css_class("flat")
        clear_all.connect("clicked", self._on_clear_all)
        header.pack_end(clear_all)

        root.append(header)

        self.search = Gtk.SearchEntry(placeholder_text="Search clipboard…")
        self.search.set_margin_top(8)
        self.search.set_margin_bottom(8)
        self.search.set_margin_start(8)
        self.search.set_margin_end(8)
        self.search.connect("search-changed", self._on_search_changed)
        self.search.connect("activate", lambda *_: self._activate_selected())
        root.append(self.search)

        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.add_css_class("boxed-list")
        self.listbox.set_margin_start(8)
        self.listbox.set_margin_end(8)
        self.listbox.set_margin_bottom(8)
        self.listbox.connect("row-activated", lambda *_: self._activate_selected())
        scroller.set_child(self.listbox)
        root.append(scroller)

        self._empty = Adw.StatusPage(
            icon_name="edit-paste-symbolic",
            title="No clipboard history",
            description="Copy some text and it will show up here.",
        )

        # --- key handling -------------------------------------------------
        # CAPTURE phase: the search box is always focused, so without this the
        # GtkText inside it would swallow Delete/Up/Down before they reached us.
        # Handled keys are consumed here; printable keys fall through to typing.
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        # Close when the window loses focus, like a native popup.
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *_: self.close())
        self.add_controller(focus)

        self.reload()
        self.search.grab_focus()

    # -- data ------------------------------------------------------------
    def reload(self, query: str | None = None) -> None:
        self._entries = db.list_entries(limit=config.SHOW_LIMIT, query=query)

        child = self.listbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt

        for entry in self._entries:
            self.listbox.append(self._build_row(entry))

        if self._entries:
            first = self.listbox.get_row_at_index(0)
            if first is not None:
                self.listbox.select_row(first)
        # (StatusPage swapping omitted for simplicity; empty list is acceptable.)

    def _build_row(self, entry: db.Entry) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row._entry = entry  # stash the model object on the widget

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(10)
        box.set_margin_end(10)

        if entry.pinned:
            pin = Gtk.Image.new_from_icon_name("view-pin-symbolic")
            pin.add_css_class("accent")
            box.append(pin)

        if entry.kind == "image":
            thumb = Gtk.Picture.new_for_filename(entry.content)
            thumb.set_content_fit(Gtk.ContentFit.CONTAIN)
            thumb.set_can_shrink(True)
            thumb.set_size_request(160, 64)
            thumb.set_halign(Gtk.Align.START)
            thumb.set_hexpand(True)
            box.append(thumb)
        else:
            text = Gtk.Label(xalign=0, hexpand=True)
            preview = entry.content.strip().splitlines()[0] if entry.content.strip() else ""
            if len(preview) > 70:
                preview = preview[:67] + "…"
            text.set_text(preview or "(whitespace)")
            text.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
            box.append(text)

        when = Gtk.Label(label=_relative_time(entry.created_at))
        when.add_css_class("dim-label")
        when.add_css_class("caption")
        box.append(when)

        row.set_child(box)
        return row

    # -- actions ---------------------------------------------------------
    def _selected_entry(self) -> db.Entry | None:
        row = self.listbox.get_selected_row()
        return getattr(row, "_entry", None) if row is not None else None

    def _activate_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        if entry.kind == "image":
            clipboard.copy_image(entry.content)
        else:
            clipboard.copy(entry.content)
        # Reusing an entry deliberately leaves its position unchanged (issue #3).
        # Close first so the compositor hands focus back to the previous window,
        # then ask the shell extension to paste into it (Win+V style).
        self.close()
        if config.AUTO_PASTE:
            clipboard.paste_into_active()

    def _move_selection(self, delta: int) -> None:
        row = self.listbox.get_selected_row()
        idx = row.get_index() if row is not None else -1
        new = max(0, min(len(self._entries) - 1, idx + delta))
        target = self.listbox.get_row_at_index(new)
        if target is not None:
            self.listbox.select_row(target)
            target.grab_focus()
            self.search.grab_focus()  # keep typing focus in the search box

    def _toggle_pin(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        db.set_pinned(entry.id, not entry.pinned)
        self.reload(self.search.get_text() or None)

    def _on_clear_all(self, _btn: Gtk.Button) -> None:
        db.clear(keep_pinned=True)
        self.reload(self.search.get_text() or None)
        self.search.grab_focus()

    def _delete_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        idx = self.listbox.get_selected_row().get_index()
        db.delete(entry.id)
        self.reload(self.search.get_text() or None)
        restore = self.listbox.get_row_at_index(min(idx, len(self._entries) - 1))
        if restore is not None:
            self.listbox.select_row(restore)

    # -- input -----------------------------------------------------------
    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self.reload(entry.get_text() or None)

    def _on_key(self, _ctrl, keyval, _keycode, state) -> bool:
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if keyval == Gdk.KEY_Down:
            self._move_selection(1)
            return True
        if keyval == Gdk.KEY_Up:
            self._move_selection(-1)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._activate_selected()
            return True
        if ctrl and keyval in (Gdk.KEY_p, Gdk.KEY_P):
            self._toggle_pin()
            return True
        if keyval == Gdk.KEY_Delete:
            self._delete_selected()
            return True
        return False
