#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "============================================================"
echo " Building INKCOPY (macOS .app)"
echo "============================================================"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install Python 3 from https://www.python.org/downloads/"
  exit 1
fi

# Generate .icns from the source PNG if missing.
if [ ! -f "$ROOT/assets/inkcopy.icns" ]; then
  echo "Generating assets/inkcopy.icns from inkcopy.png..."
  bash "$ROOT/scripts/build_icns.sh"
fi

echo "Installing dependencies..."
python3 -m pip install --upgrade pip pyinstaller
python3 -m pip install -r "$ROOT/requirements.txt"

echo "Cleaning previous build..."
rm -rf build dist

echo "Running PyInstaller..."
python3 -m PyInstaller --noconfirm --clean INKCOPY.spec

echo
echo "============================================================"
echo " Build OK"
echo "============================================================"
echo " Output : $ROOT/dist/INKCOPY.app"
echo " Tip    : Move INKCOPY.app to /Applications, then grant"
echo "          Accessibility permission in System Settings →"
echo "          Privacy & Security → Accessibility."
echo "============================================================"
