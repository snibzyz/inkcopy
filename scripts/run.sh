#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Starting INKCOPY..."

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$ROOT/inkcopy.py"
fi

echo "ERROR: python3 not found. Run scripts/install.sh first."
exit 1
