# LinPaste

A clipboard history manager for **Ubuntu (Wayland / GNOME)** — the `Win + V`
experience Windows has, but for Linux.

Linux gives you only a single clipboard slot: copy something new and the previous
item is gone. LinPaste runs quietly in the background, remembers everything you
copy — **text and images** — and pops up a searchable history when you press
**Super + V**. Pick an item and it's pasted straight into wherever you were
typing (and left on your clipboard, so you can `Ctrl + V` it again).

## How it works

```
GNOME Shell extension  ──►  linpaste store  ──►  SQLite history.db
 (polls clipboard ~1s)       (dedup + trim)              │
                                                         ▼ read
        Super+V (GNOME shortcut) ──► linpaste show (GTK4 popup) ──► wl-copy
```

- **Capture** — On GNOME, Mutter exposes no data-control Wayland protocol, so
  background tools like `wl-paste --watch` / `cliphist` **cannot** read the
  clipboard (only the focused app, or the shell, can). LinPaste therefore ships a
  tiny GNOME Shell extension that polls the clipboard and pipes each new copy to
  `linpaste store`. This is the same approach GPaste and Clipboard Indicator use.
- **Storage** — SQLite at `~/.local/share/linpaste/history.db`. Identical
  re-copies are de-duplicated; history is capped (default 500 unpinned entries).
  Copied **images** are saved as files under `~/.local/share/linpaste/images/`
  and referenced from the database.
- **Popup** — a GTK4 / libadwaita window with live search and keyboard nav.
  Text entries show a preview; image entries show a thumbnail and are copied
  back as images on `Enter`. The trash button in the header clears all history.
- **Hotkey** — bound through GNOME (Wayland blocks in-app global hotkeys), so
  GNOME launches `linpaste show` on `Super + V`.
- **Privacy** — clipboard contents flagged by password managers
  (`x-kde-passwordManagerHint`) are skipped.

## Install

### Option A — `.deb` package (recommended for a fresh device)

```bash
sudo apt install ./linpaste_0.2.0_all.deb
```

`apt` pulls in every dependency (`wl-clipboard`, GTK4, libadwaita, GNOME Shell).
Then, **per user**:

```bash
# log out and back in once (so GNOME loads the capture extension), then:
linpaste setup     # binds Super+V and enables capture
linpaste status    # should say State: ACTIVE
```

Don't have the `.deb` yet? Build one from this repo:

```bash
./packaging/build-deb.sh        # -> dist/linpaste_<version>_all.deb
```

### Option B — from source (for development)

```bash
./install.sh       # apt deps + pip install + extension + hotkey
```

> **Either way: log out and back in once** after installing, so GNOME loads the
> capture extension (on Wayland the shell can't hot-load a new extension's
> files). Then `linpaste setup` (or `linpaste enable`) turns capture on.

## Usage

| Action | Key |
|--------|-----|
| Open popup | `Super + V` |
| Filter | just start typing |
| Move selection | `↑` / `↓` |
| Copy, close & paste into the previous window | `Enter` |
| Pin / unpin | `Ctrl + P` |
| Delete selected entry | `Delete` |
| Clear all history | trash button (top-right) |
| Close | `Esc` |

CLI:

```bash
linpaste list            # print recent history
linpaste list -q foo     # filter
linpaste clear           # wipe history (keeps pinned)
linpaste clear --all     # wipe everything
linpaste show            # open the popup
linpaste status          # check the capture extension is active
```

## Requirements

Ubuntu/GNOME on Wayland, Python ≥ 3.10. System packages (installed by
`install.sh`): `wl-clipboard`, `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`.

## Not yet supported

Arbitrary files, encryption-at-rest. See the project plan for the roadmap.

## License

MIT
