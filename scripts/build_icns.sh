#!/usr/bin/env bash
# Generate assets/inkcopy.icns from assets/inkcopy.png using macOS tooling.
# Requires: macOS (sips + iconutil are preinstalled).
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/assets/inkcopy.png"
OUT="$ROOT/assets/inkcopy.icns"

if [ ! -f "$SRC" ]; then
  echo "ERROR: $SRC not found"
  exit 1
fi

if ! command -v sips >/dev/null 2>&1 || ! command -v iconutil >/dev/null 2>&1; then
  echo "ERROR: sips/iconutil not found. This script must run on macOS."
  exit 1
fi

TMP="$(mktemp -d)"
ICONSET="$TMP/inkcopy.iconset"
mkdir -p "$ICONSET"

# Apple-recommended sizes for .icns
sips -z 16   16   "$SRC" --out "$ICONSET/icon_16x16.png"      >/dev/null
sips -z 32   32   "$SRC" --out "$ICONSET/icon_16x16@2x.png"   >/dev/null
sips -z 32   32   "$SRC" --out "$ICONSET/icon_32x32.png"      >/dev/null
sips -z 64   64   "$SRC" --out "$ICONSET/icon_32x32@2x.png"   >/dev/null
sips -z 128  128  "$SRC" --out "$ICONSET/icon_128x128.png"    >/dev/null
sips -z 256  256  "$SRC" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
sips -z 256  256  "$SRC" --out "$ICONSET/icon_256x256.png"    >/dev/null
sips -z 512  512  "$SRC" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
sips -z 512  512  "$SRC" --out "$ICONSET/icon_512x512.png"    >/dev/null
sips -z 1024 1024 "$SRC" --out "$ICONSET/icon_512x512@2x.png" >/dev/null

iconutil -c icns -o "$OUT" "$ICONSET"
rm -rf "$TMP"

echo "Wrote $OUT"
