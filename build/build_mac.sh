#!/usr/bin/env bash
# Build Warrior IPTV Player.app for macOS.
#
# Usage:
#   bash build/build_mac.sh            # build .app
#   bash build/build_mac.sh --dmg      # build .app + wrap in a DMG
#
# Requirements: Python 3.10+, pip, Homebrew mpv
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$REPO_ROOT/.venv"
DIST="$REPO_ROOT/dist"
APP="$DIST/Warrior IPTV Player.app"
BUILD_DMG=false

for arg in "$@"; do
  [[ "$arg" == "--dmg" ]] && BUILD_DMG=true
done

# ── Sanity checks ────────────────────────────────────────────────────────────
if [[ "$(uname)" != "Darwin" ]]; then
  echo "Error: this script must run on macOS." >&2
  exit 1
fi

if ! command -v brew &>/dev/null; then
  echo "Error: Homebrew is not installed. Run setup_mac.sh first." >&2
  exit 1
fi

# Ensure libmpv is present
BREW_PREFIX="$(brew --prefix)"
LIBMPV=""
for d in "$BREW_PREFIX/lib" "/usr/local/lib"; do
  [[ -f "$d/libmpv.dylib" ]] && { LIBMPV="$d/libmpv.dylib"; break; }
done
if [[ -z "$LIBMPV" ]]; then
  echo "Error: libmpv.dylib not found. Run: brew install mpv" >&2
  exit 1
fi
echo "Using libmpv: $LIBMPV"

# ── Virtual environment ──────────────────────────────────────────────────────
if [[ ! -d "$VENV" ]]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV"
fi
source "$VENV/bin/activate"

echo "Installing / upgrading dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r "$REPO_ROOT/requirements.txt"
pip install --quiet "pyinstaller>=6.6"

# ── Optional: generate icon.icns ────────────────────────────────────────────
ICNS="$REPO_ROOT/resources/icon.icns"
ICO="$REPO_ROOT/resources/icon.ico"
if [[ ! -f "$ICNS" && -f "$ICO" ]]; then
  echo "Generating icon.icns from icon.ico..."
  bash "$REPO_ROOT/scripts/create_icns.sh" "$ICO" "$ICNS" || true
fi

# ── PyInstaller ──────────────────────────────────────────────────────────────
echo "Running PyInstaller..."
cd "$REPO_ROOT"
pyinstaller packaging/mac.spec --noconfirm --distpath "$DIST" --workpath "$REPO_ROOT/build/pyi-work-mac"

echo ""
echo "Build complete:  $APP"

# ── Optional DMG ─────────────────────────────────────────────────────────────
if [[ "$BUILD_DMG" == true ]]; then
  DMG="$DIST/WarriorIPTV.dmg"
  echo "Creating DMG: $DMG"
  # Create a temporary sparse image, copy the .app, add an /Applications symlink
  TMP_DMG="$DIST/tmp_warrior.dmg"
  rm -f "$TMP_DMG" "$DMG"
  hdiutil create -size 256m -fs HFS+ -volname "Warrior IPTV Player" "$TMP_DMG" -quiet
  MOUNT_POINT="$(hdiutil attach "$TMP_DMG" -readwrite -nobrowse -quiet | awk 'END{print $NF}')"
  cp -R "$APP" "$MOUNT_POINT/"
  ln -s /Applications "$MOUNT_POINT/Applications"
  hdiutil detach "$MOUNT_POINT" -quiet
  hdiutil convert "$TMP_DMG" -format UDZO -o "$DMG" -quiet
  rm -f "$TMP_DMG"
  echo "DMG ready:       $DMG"
fi

echo ""
echo "────────────────────────────────────────────────────────"
echo "  To run the app:"
echo "    open \"$APP\""
echo ""
echo "  If macOS blocks it (unverified developer):"
echo "    xattr -cr \"$APP\""
echo "    open \"$APP\""
echo "────────────────────────────────────────────────────────"
