#!/usr/bin/env bash
# Packages dist/INKCOPY.app into INKCOPY-vX.X.X.dmg with a drag-to-Applications layout.
# Also ad-hoc codesigns the bundle — this gives the binary a stable signature so the
# macOS TCC database (which keys permissions to signature) stops invalidating
# Accessibility grants between rebuilds. That alone fixes most "toggle ON but
# Cmd+V doesn't fire" reports.
#
# Usage:   bash scripts/build_dmg.sh        # builds .app first if missing, then .dmg
#          bash scripts/build_dmg.sh --skip-build  # uses existing dist/INKCOPY.app
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SKIP_BUILD=0
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=1 ;;
  esac
done

APP_PATH="$ROOT/dist/INKCOPY.app"
VERSION="$(python3 -c "import re; print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', open('inkcopy.py', encoding='utf-8').read()).group(1))")"
DMG_NAME="INKCOPY-v${VERSION}.dmg"
DMG_PATH="$ROOT/dist/${DMG_NAME}"
STAGE_DIR="$ROOT/dist/_dmg_stage"

echo "============================================================"
echo " Packaging INKCOPY v${VERSION} → ${DMG_NAME}"
echo "============================================================"

if [ "$SKIP_BUILD" -eq 0 ]; then
  if [ ! -d "$APP_PATH" ]; then
    echo "[1/4] Building dist/INKCOPY.app..."
    bash "$ROOT/scripts/build.sh"
  else
    echo "[1/4] Reusing existing dist/INKCOPY.app (pass nothing to rebuild from scratch — or use scripts/build.sh)"
  fi
else
  if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: --skip-build set but $APP_PATH does not exist"
    exit 1
  fi
  echo "[1/4] Skipping build, reusing $APP_PATH"
fi

echo "[2/4] Ad-hoc codesigning bundle (stabilizes TCC entry across rebuilds)..."
# --force replaces any existing signature; --deep covers nested frameworks/libs
# from PyInstaller's bundling of Qt + pynput's Quartz support.
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --verbose "$APP_PATH" || echo "WARN: codesign verify reported issues (often safe for ad-hoc)"

echo "[3/4] Staging DMG contents..."
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"
cp -R "$APP_PATH" "$STAGE_DIR/"
ln -s /Applications "$STAGE_DIR/Applications"

echo "[4/4] Creating ${DMG_NAME}..."
rm -f "$DMG_PATH"
hdiutil create \
  -volname "INKCOPY ${VERSION}" \
  -srcfolder "$STAGE_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

rm -rf "$STAGE_DIR"

echo
echo "============================================================"
echo " DMG OK"
echo "============================================================"
echo " Output : ${DMG_PATH}"
echo
echo " IMPORTANT for testers running into Cmd+V issues:"
echo " 1. Drag INKCOPY.app to /Applications"
echo " 2. Right-click → Open (first time only)"
echo " 3. System Settings → Privacy & Security → Accessibility:"
echo "    if INKCOPY was already in the list from a previous build,"
echo "    REMOVE it (−) and re-add (+) the new copy. Then Quit & reopen."
echo "    (TCC keys permission to binary signature — old entry blocks the new bundle.)"
echo "============================================================"
