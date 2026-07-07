#!/bin/bash
# Literature Search - macOS launcher (double-click to run)
cd "$(dirname "$0")" || exit 1
APPDIR="$(pwd)/app"

echo "============================================"
echo "  Literature Search - macOS launcher"
echo "============================================"

# Return 0 if the given python command exists and is version >= 3.9
is_compatible() {
  command -v "$1" >/dev/null 2>&1 || return 1
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' >/dev/null 2>&1
}

# ---- 1. Find a COMPATIBLE Python (3.9+) ------------------------------
PY=""
for cand in python3 python3.12 python3.11 python3.10 python3.9 python; do
  if is_compatible "$cand"; then PY="$cand"; break; fi
done

# ---- 2. If none, try to install a modern Python ----------------------
if [ -z "$PY" ]; then
  echo "No compatible Python found (needs 3.9 or newer)."
  if command -v brew >/dev/null 2>&1; then
    echo "Installing Python 3 with Homebrew..."
    brew install python
    is_compatible python3 && PY="python3"
  fi
fi

if [ -z "$PY" ]; then
  echo ""
  echo "Please install Python 3 from https://www.python.org/downloads/macos/"
  echo "(download, open the .pkg, click through), then double-click this file again."
  read -n 1 -s -r -p "Press any key to close."
  exit 1
fi

echo "Using Python: $PY ($($PY --version 2>&1))"

# ---- 3. Create the virtual environment (the "container") -------------
if [ ! -x "$APPDIR/.venv/bin/python" ]; then
  echo "Creating virtual environment..."
  "$PY" -m venv "$APPDIR/.venv"
fi
VENVPY="$APPDIR/.venv/bin/python"

# ---- 4. Install required packages (only the first time) --------------
if [ ! -f "$APPDIR/.venv/.installed" ]; then
  echo "Installing required packages (one-time)..."
  "$VENVPY" -m pip install --upgrade pip
  if ! "$VENVPY" -m pip install -r "$APPDIR/requirements.txt"; then
    echo ""
    echo "Package installation failed. Check your internet connection and re-run."
    read -n 1 -s -r -p "Press any key to close."
    exit 1
  fi
  touch "$APPDIR/.venv/.installed"
fi

# ---- 5. Start the app ------------------------------------------------
echo "Starting the app... a browser tab will open shortly."
"$VENVPY" "$APPDIR/app.py"

read -n 1 -s -r -p "App stopped. Press any key to close."
