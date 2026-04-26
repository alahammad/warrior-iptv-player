#!/usr/bin/env bash
# Build a fully self-contained Warrior IPTV Player.app for macOS.
#
# The resulting .app bundles Python, all Python packages, libmpv, and every
# transitive C library (FFmpeg, libass, …) so end-users need nothing installed.
#
# Usage:
#   bash build/build_mac.sh          # → dist/Warrior IPTV Player.app
#   bash build/build_mac.sh --dmg    # → dist/WarriorIPTV.dmg  (drag-to-install)
#
# Build requirements (developer machine only, not end-user):
#   - macOS 11+
#   - Homebrew  (brew install mpv)
#   - Python 3.10+ reachable as python3
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$REPO_ROOT/.venv"
DIST="$REPO_ROOT/dist"
APP="$DIST/Warrior IPTV Player.app"
APP_MACOS="$APP/Contents/MacOS"
BUILD_DMG=false

for arg in "$@"; do
  [[ "$arg" == "--dmg" ]] && BUILD_DMG=true
done

# ── Platform check ────────────────────────────────────────────────────────────
if [[ "$(uname)" != "Darwin" ]]; then
  echo "Error: this script must run on macOS." >&2; exit 1
fi

# ── Locate libmpv.dylib (developer machine requirement) ───────────────────────
if ! command -v brew &>/dev/null; then
  echo "Error: Homebrew not found — install it, then run: brew install mpv" >&2
  exit 1
fi
BREW_PREFIX="$(brew --prefix)"
LIBMPV=""
for d in "$BREW_PREFIX/lib" "/usr/local/lib"; do
  [[ -f "$d/libmpv.dylib" ]] && { LIBMPV="$d/libmpv.dylib"; break; }
done
if [[ -z "$LIBMPV" ]]; then
  echo "Error: libmpv.dylib not found. Run: brew install mpv" >&2; exit 1
fi
echo "libmpv : $LIBMPV"

# ── Virtual environment + dependencies ────────────────────────────────────────
if [[ ! -d "$VENV" ]]; then
  echo "Creating .venv..."
  python3 -m venv "$VENV"
fi
source "$VENV/bin/activate"

pip install --quiet --upgrade pip
pip install --quiet -r "$REPO_ROOT/requirements.txt"
pip install --quiet "pyinstaller>=6.6"
# delocate walks the bundle's dylib tree and copies every non-system dependency
# into Contents/MacOS/, then rewrites all @rpath/@loader_path references so the
# bundle is fully self-contained — no Homebrew required on end-user machines.
pip install --quiet "delocate>=0.11"

# ── Generate icon.icns if missing ─────────────────────────────────────────────
ICNS="$REPO_ROOT/resources/icon.icns"
ICO="$REPO_ROOT/resources/icon.ico"
if [[ ! -f "$ICNS" && -f "$ICO" ]]; then
  echo "Generating icon.icns..."
  bash "$REPO_ROOT/scripts/create_icns.sh" "$ICO" "$ICNS" || true
fi

# ── PyInstaller ───────────────────────────────────────────────────────────────
echo "Running PyInstaller..."
cd "$REPO_ROOT"
pyinstaller packaging/mac.spec \
  --noconfirm \
  --distpath "$DIST" \
  --workpath "$REPO_ROOT/build/pyi-work-mac"

# ── delocate — bundle ALL transitive dylib dependencies ──────────────────────
# Without this step, libmpv.dylib's own dependencies (FFmpeg libs, libass, …)
# are NOT included, so the app fails on any machine without Homebrew.
echo "Bundling dylib dependencies with delocate..."
delocate-path "$APP_MACOS" \
  --lib-path "$APP_MACOS" \
  -v 2>&1 | grep -E "^(Copying|Fixed)" || true

# Patch the main executable's rpath so it finds the bundled libs at runtime
# (delocate does this automatically, but an explicit add is harmless insurance).
EXE="$APP_MACOS/WarriorIPTV"
if [[ -f "$EXE" ]]; then
  install_name_tool -add_rpath "@executable_path" "$EXE" 2>/dev/null || true
fi

echo "App : $APP"

# ── DMG (optional) ────────────────────────────────────────────────────────────
if [[ "$BUILD_DMG" == true ]]; then
  DMG="$DIST/WarriorIPTV.dmg"
  TMP_DMG="$DIST/_tmp_warrior.dmg"
  echo "Creating $DMG ..."
  rm -f "$TMP_DMG" "$DMG"

  # Size estimate: actual app size + 20 % headroom
  APP_MB=$(du -sm "$APP" | awk '{print $1}')
  IMG_MB=$(( APP_MB * 12 / 10 + 32 ))

  hdiutil create -size "${IMG_MB}m" -fs HFS+ \
    -volname "Warrior IPTV Player" "$TMP_DMG" -quiet
  MOUNT_POINT="$(hdiutil attach "$TMP_DMG" -readwrite -nobrowse -quiet \
    | awk 'END{print $NF}')"
  cp -R "$APP" "$MOUNT_POINT/"
  ln -s /Applications "$MOUNT_POINT/Applications"
  hdiutil detach "$MOUNT_POINT" -quiet
  hdiutil convert "$TMP_DMG" -format UDZO -imagekey zlib-level=9 \
    -o "$DMG" -quiet
  rm -f "$TMP_DMG"
  echo "DMG : $DMG"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "  Build complete — self-contained, no Homebrew needed"
echo ""
if [[ "$BUILD_DMG" == true ]]; then
  echo "  Distribute:  dist/WarriorIPTV.dmg"
  echo "  Install:     drag .app to /Applications"
else
  echo "  App:  $APP"
fi
echo ""
echo "  First launch on a new Mac (Gatekeeper bypass):"
echo "    xattr -cr \"$APP\""
echo "    open \"$APP\""
echo "══════════════════════════════════════════════════════"
