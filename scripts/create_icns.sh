#!/usr/bin/env bash
# Convert an .ico file to a macOS .icns file.
# Requires macOS tools: sips, iconutil (both pre-installed on macOS).
#
# Usage: bash scripts/create_icns.sh <input.ico> <output.icns>
set -euo pipefail

SRC="${1:-}"
DST="${2:-}"

if [[ -z "$SRC" || -z "$DST" ]]; then
  echo "Usage: $0 <input.ico> <output.icns>" >&2
  exit 1
fi

if [[ ! -f "$SRC" ]]; then
  echo "Error: source file not found: $SRC" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
ICONSET="$TMP_DIR/AppIcon.iconset"
mkdir -p "$ICONSET"

# Extract a reasonably sized PNG from the .ico using sips
EXTRACTED_PNG="$TMP_DIR/src.png"
sips -s format png "$SRC" --out "$EXTRACTED_PNG" &>/dev/null

# Generate the required iconset sizes
declare -a SIZES=(16 32 64 128 256 512)
for SIZE in "${SIZES[@]}"; do
  sips -z "$SIZE" "$SIZE" "$EXTRACTED_PNG" --out "$ICONSET/icon_${SIZE}x${SIZE}.png" &>/dev/null
  DOUBLE=$((SIZE * 2))
  sips -z "$DOUBLE" "$DOUBLE" "$EXTRACTED_PNG" --out "$ICONSET/icon_${SIZE}x${SIZE}@2x.png" &>/dev/null
done

iconutil -c icns "$ICONSET" -o "$DST"
rm -rf "$TMP_DIR"

echo "Created: $DST"
