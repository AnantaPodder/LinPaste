#!/usr/bin/env bash
# One-shot installer for LinPaste on Ubuntu (Wayland/GNOME).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXT_UUID="linpaste-capture@anantapodder.github.io"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"

echo "==> Installing system dependencies (sudo required)…"
sudo apt-get update
sudo apt-get install -y wl-clipboard python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-pip

echo "==> Installing the linpaste package…"
pip3 install --user --break-system-packages "$HERE"

# pip --user installs scripts to ~/.local/bin; the hotkey command and the shell
# extension both look for `linpaste` there, so make sure it's on PATH.
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "   NOTE: add \$HOME/.local/bin to your PATH (e.g. in ~/.profile)";;
esac

echo "==> Installing the GNOME Shell capture extension…"
mkdir -p "$EXT_DIR"
cp -r "$HERE/extension/$EXT_UUID/." "$EXT_DIR/"

echo "==> Binding the Super+V hotkey…"
# `linpaste setup` binds the hotkey now and attempts to enable the extension.
# Enabling won't stick until the shell has scanned the new folder (post-logout),
# so we re-run setup after logging back in — see the message below.
linpaste setup || true

echo
echo "Done — ONE manual step remains:"
echo
echo "  1. Log out and back in  (Wayland can't hot-load a new extension)."
echo "  2. Run:  linpaste setup   (enables capture; hotkey is already bound)."
echo "  3. Check: linpaste status   (should say State: ACTIVE)."
echo
echo "Then copy some text and press Super+V."
