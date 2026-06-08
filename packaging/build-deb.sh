#!/usr/bin/env bash
# Build a .deb for LinPaste using only dpkg-deb (no extra build tooling needed).
#
#   ./packaging/build-deb.sh
#   -> dist/linpaste_<version>_all.deb
#
# Install on a fresh device with:
#   sudo apt install ./linpaste_<version>_all.deb
#   # log out / back in, then:
#   linpaste setup
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT_UUID="linpaste-capture@anantapodder.github.io"

# Pull the version straight from pyproject.toml so there's one source of truth.
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$HERE/pyproject.toml" | head -1)"
[ -n "$VERSION" ] || { echo "could not read version from pyproject.toml" >&2; exit 1; }

PKG="linpaste"
STAGE="$HERE/packaging/build/${PKG}_${VERSION}"
OUT="$HERE/dist/${PKG}_${VERSION}_all.deb"

echo "==> Staging ${PKG} ${VERSION}"
rm -rf "$STAGE"
mkdir -p \
  "$STAGE/DEBIAN" \
  "$STAGE/usr/bin" \
  "$STAGE/usr/share/linpaste" \
  "$STAGE/usr/share/gnome-shell/extensions" \
  "$STAGE/usr/share/doc/linpaste"

# --- Python package ----------------------------------------------------------
# Ship the package under /usr/share/linpaste and run it via PYTHONPATH, so we
# never touch the system dist-packages tree.
cp -r "$HERE/linpaste" "$STAGE/usr/share/linpaste/linpaste"
find "$STAGE/usr/share/linpaste" -name '__pycache__' -type d -prune -exec rm -rf {} +

# --- launcher ----------------------------------------------------------------
cat > "$STAGE/usr/bin/linpaste" <<'EOF'
#!/bin/sh
# LinPaste launcher (installed by the .deb).
export PYTHONPATH="/usr/share/linpaste${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m linpaste "$@"
EOF
chmod 0755 "$STAGE/usr/bin/linpaste"

# --- GNOME Shell extension (system-wide) ------------------------------------
cp -r "$HERE/extension/$EXT_UUID" \
      "$STAGE/usr/share/gnome-shell/extensions/$EXT_UUID"

# --- docs --------------------------------------------------------------------
cp "$HERE/README.md" "$STAGE/usr/share/doc/linpaste/README.md"
cat > "$STAGE/usr/share/doc/linpaste/copyright" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: linpaste

Files: *
Copyright: 2026 Ananta Podder
License: MIT
EOF

# --- control -----------------------------------------------------------------
# Installed-Size in KiB (rough, for apt's UI).
SIZE_KB="$(du -ks "$STAGE/usr" | cut -f1)"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, wl-clipboard, gnome-shell
Installed-Size: $SIZE_KB
Maintainer: Ananta Podder <31305962+AnantaPodder@users.noreply.github.com>
Description: Clipboard history manager for Ubuntu (Wayland/GNOME)
 LinPaste records your clipboard history and shows it in a Super+V popup,
 like the Windows clipboard manager. It ships a small GNOME Shell extension
 that captures every copy (GNOME exposes no clipboard-watch protocol, so the
 shell must do it) and a GTK4 popup to search and re-copy past items.
EOF

# --- postinst: per-user setup can't run as root, so just guide the user ------
cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    echo ""
    echo "LinPaste installed. Two steps to finish (per user):"
    echo "  1. Log out and back in  (so GNOME loads the capture extension)."
    echo "  2. Run:  linpaste setup   (binds Super+V and enables capture)."
    echo ""
fi
exit 0
EOF
chmod 0755 "$STAGE/DEBIAN/postinst"

# --- build -------------------------------------------------------------------
mkdir -p "$HERE/dist"
echo "==> Building $OUT"
dpkg-deb --root-owner-group --build "$STAGE" "$OUT"

echo
echo "Built: $OUT"
echo "Inspect with:  dpkg-deb -I '$OUT'  and  dpkg-deb -c '$OUT'"
echo "Install with:  sudo apt install '$OUT'"
