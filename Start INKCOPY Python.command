#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/inkcopy.py" ]; then
  ROOT="$SCRIPT_DIR"
else
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
cd "$ROOT"

echo "============================================================"
echo " Starting INKCOPY Python"
echo "============================================================"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found."
  echo "Install Python 3 from https://www.python.org/downloads/ or Homebrew."
  echo
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "Creating local Python environment..."
  python3 -m venv "$ROOT/.venv"
fi

PY="$ROOT/.venv/bin/python"

set +e
"$PY" - <<'PY'
import importlib.util
import sys

missing = []
for mod, pkg in [
    ("natsort", "natsort"),
    ("PyQt6", "PyQt6"),
    ("pynput", "pynput"),
]:
    if importlib.util.find_spec(mod) is None:
        missing.append(pkg)

if sys.platform == "darwin":
    for mod, pkg in [
        ("AppKit", "pyobjc-framework-Cocoa"),
        ("Quartz", "pyobjc-framework-Quartz"),
    ]:
        if importlib.util.find_spec(mod) is None:
            missing.append(pkg)

if missing:
    print("MISSING_DEPS:" + " ".join(missing))
    raise SystemExit(42)
PY

status=$?
set -e
if [ "$status" -eq 42 ]; then
  echo
  echo "Installing missing Python dependencies..."
  "$PY" -m pip install --upgrade pip
  "$PY" -m pip install -r "$ROOT/requirements.txt"
fi

exec "$PY" "$ROOT/inkcopy.py"
