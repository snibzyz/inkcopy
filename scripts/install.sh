#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "========================================="
echo "  INKCOPY - install dependencies (macOS/Linux)"
echo "========================================="

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found."
  echo "  macOS: brew install python   (or download from https://www.python.org/downloads/)"
  exit 1
fi

python3 -m pip install --upgrade pip
python3 -m pip install -r "$ROOT/requirements.txt"

echo
echo "Done. Run:  scripts/run.sh"
