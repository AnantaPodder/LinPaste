# LinPaste Roadmap

This document tracks where LinPaste is, where it's going, and why. It's informed
by what mature clipboard managers (GPaste, CopyQ, Windows 11's Win+V, Maccy,
Ditto) already do well, filtered through LinPaste's goal: **the cleanest possible
"Win+V for Linux" on Wayland/GNOME, with an honest path to other desktops.**

Last reviewed: 2026-06-09 · Current release: **v0.2.0**

---

## Design principles

These constrain every item below:

1. **Local-first & private.** History never leaves the machine unless the user
   explicitly turns on sync. Password-manager content is skipped by default.
2. **Keyboard-first.** Every common action must be reachable without the mouse.
3. **Boring storage.** Plain SQLite + files on disk, XDG paths, easy to inspect,
   back up, or delete. No proprietary blobs.
4. **Light capture path.** The hot path (`linpaste store`, run once per copy)
   must stay fast and never import GTK.
5. **Graceful degradation.** Missing a hotkey, extension, or DE feature should
   warn clearly, never crash; the core copy/paste must still work.

---

## Where we are (shipped in v0.2.0)

- ✅ Background **capture** via a GNOME Shell extension (polls the clipboard ~1s).
- ✅ **Text and image** history in SQLite (`~/.local/share/linpaste/`).
- ✅ **De-duplication** (re-copy bumps the existing row) and **history cap / trim**.
- ✅ **GTK4 / libadwaita popup** with live search and keyboard navigation.
- ✅ **Pin / unpin** entries (pinned never trimmed).
- ✅ **Auto-paste** — synthesize `Ctrl+V` into the previously focused window.
- ✅ **Delete entry** and **Clear all**.
- ✅ **Password-manager privacy skip** (`x-kde-passwordManagerHint`).
- ✅ **CLI**: `store`, `show`, `list`, `clear`, `status`, `enable`, `setup`.
- ✅ **`.deb` packaging** + from-source installer.

---

## Milestones

### v0.3 — Polish the daily-driver experience
*Goal: make the existing core feel finished. No new subsystems.*

- [ ] **Persistent config file** (`~/.config/linpaste/config.toml`) replacing the
      env-var-only settings; env vars still override. Single source of truth for
      `max_history`, `show_limit`, `auto_paste`, etc.
- [ ] **Preferences window** (libadwaita) — history size, auto-paste toggle,
      sensitive-skip toggle, launch-on-login. No more editing env vars.
- [ ] **Per-item context menu / edit** — edit text before pasting, copy without
      pasting, pin, delete, "copy as plain text".
- [ ] **Better search** — case-insensitive (done via LIKE today) plus optional
      fuzzy matching and match highlighting in the list.
- [ ] **Time-stamps in the UI** — "5 min ago" relative labels per entry.
- [ ] **Keyboard refinements** — number keys (1–9) to paste the Nth item,
      `Ctrl+Enter` to copy-without-paste.

### v0.4 — Smarter content
*Goal: treat clipboard items as typed data, not just a string blob.*

- [ ] **Content-type detection & badges** — URL, color (`#rrggbb`), email,
      file path, code-ish blocks. Show an icon/badge per row.
- [ ] **Type filters** — filter the popup to text / image / link / file
      (chips along the top, à la Maccy/CopyQ).
- [ ] **Rich-text / HTML awareness** — already store `html`; offer
      "paste as rich text" vs "paste as plain text".
- [ ] **Per-source tracking** — record the foreground app/window title at copy
      time (via the capture extension) and make it searchable / filterable.
- [ ] **Quick actions on detected types** — open URL, preview color swatch.

### v0.5 — Snippets & templates
*Goal: the most-requested power feature across CopyQ / Ditto / Windows 11.*

- [ ] **Saved snippets** — promote any entry to a named, permanent snippet
      distinct from rolling history.
- [ ] **Placeholder expansion** — `{{date}}`, `{{time}}`, `{{clipboard}}`,
      `{{cursor}}` expanded on paste.
- [ ] **Snippet groups / quick-pick** — categorize and search snippets
      separately from history.

### v0.6 — Security & trust
*Goal: make it safe to keep sensitive history, and easy to keep it clean.*

- [ ] **Encryption at rest** — optional encrypted DB / image store
      (e.g. SQLCipher or app-level AES-256), unlocked per session.
- [ ] **Exclude-list** — never record from configured apps (password managers,
      terminals, banking sites) by window class / title.
- [ ] **Auto-expiry** — drop unpinned entries older than N days.
- [ ] **Incognito / pause capture** — toggle to stop recording temporarily
      (tray/menu and CLI), with a clear indicator.
- [ ] **"Wipe now" panic action** — one keystroke to clear everything, including
      backing image files.

### v0.7 — Reach beyond GNOME
*Goal: stop being GNOME-only without compromising the GNOME experience.*

- [ ] **wlroots / generic Wayland backend** — use `wl-paste --watch` where the
      `wlr-data-control` protocol exists (Sway, Hyprland, KDE Plasma 6), so no
      shell extension is needed there.
- [ ] **KDE Plasma support** — capture + global shortcut wiring for Plasma.
- [ ] **X11 fallback** — optional support for legacy X11 sessions.
- [ ] **Pluggable capture backends** — pick the right one automatically per
      session; document the matrix.

### v0.8 — Sync (opt-in)
*Goal: Windows-11-style "it follows me to my other machine" — privately.*

- [ ] **Local network sync** — peer-to-peer over LAN, end-to-end encrypted,
      no third-party server.
- [ ] **File-based sync** — point history at a synced folder
      (Syncthing / Nextcloud / Dropbox) à la CopyQ tabs.
- [ ] **Conflict handling & device identity** — sane merge of histories.

### Backlog / exploratory
*Not committed — captured so they're not lost.*

- [ ] **File/arbitrary-MIME entries** — copy actual files, not just text/images.
- [ ] **OCR on images** — make screenshots text-searchable.
- [ ] **Multiple clipboards / tabs** (CopyQ-style organization).
- [ ] **Scripting hooks** — run a user command on each new clip.
- [ ] **Emoji / symbol picker** integrated into the popup.
- [ ] **Themes & layout options** for the popup.
- [ ] **GNOME Shell tray indicator** with recent items menu.
- [ ] **Flatpak distribution** alongside the `.deb`.

---

## Engineering / project health
*Cross-cutting work that should land alongside features, not after.*

- [ ] **Test suite** — unit tests for `db`/`config`/`clipboard` (pure logic),
      plus a headless harness for the store→list→trim path.
- [ ] **CI** — lint + tests on push (GitHub Actions); build the `.deb` on tag.
- [ ] **DB migrations framework** — the ad-hoc `_ensure_kind_column` shim won't
      scale; introduce a small versioned-migration helper before v0.4's schema
      changes (source app, content type, snippets).
- [ ] **Structured logging & `linpaste doctor`** — one command that diagnoses
      capture/hotkey/extension state and prints actionable fixes.
- [ ] **Packaging for more distros** — PPA and/or Flatpak; AUR for Arch users.
- [ ] **Documentation** — architecture doc, contribution guide, screenshots/GIF.

---

## How this maps to competitors

| Capability                | GPaste | CopyQ | Win+V | LinPaste today | LinPaste target |
|---------------------------|:------:|:-----:|:-----:|:--------------:|:---------------:|
| Text history              |  ✅    |  ✅   |  ✅   |   ✅           | ✅              |
| Image history             |  ✅    |  ✅   |  ✅   |   ✅           | ✅              |
| Pinning                   |  ✅    |  ✅   |  ✅   |   ✅           | ✅              |
| Search                    |  ✅    |  ✅   |  ⚠️   |   ✅           | ✅ (fuzzy)      |
| Auto-paste                |  ✅    |  ✅   |  ✅   |   ✅           | ✅              |
| Password skip             |  ✅    |  ⚠️   |  —    |   ✅           | ✅ (+exclude)   |
| Snippets / templates      |  ⚠️    |  ✅   |  ⚠️   |   —            | ✅ (v0.5)       |
| Encryption at rest        |  ⚠️    |  ✅   |  —    |   —            | ✅ (v0.6)       |
| Content-type filters      |  ⚠️    |  ✅   |  ⚠️   |   —            | ✅ (v0.4)       |
| Cross-device sync         |  —     |  ✅*  |  ✅   |   —            | ✅ (v0.8)       |
| File entries              |  ✅    |  ✅   |  —    |   —            | backlog         |
| Non-GNOME desktops        |  —     |  ✅   |  —    |   —            | ✅ (v0.7)       |

`⚠️` = partial / via add-on. `*` CopyQ sync is via synced folders.

---

*This roadmap is a living document — milestones may be reordered as feedback
arrives. Dates are intentionally omitted; order signals priority.*
