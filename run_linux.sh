#!/bin/bash
# Literature Search - Linux launcher
# Run by double-clicking (mark executable first) or:  bash run_linux.sh
cd "$(dirname "$0")" || exit 1
APPDIR="$(pwd)/app"

echo "============================================"
echo "  Literature Search - Linux launcher"
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

# ---- 2. If none, try to install a modern Python (needs sudo) ---------
if [ -z "$PY" ]; then
  echo "No compatible Python found (needs 3.9 or newer). Attempting to install..."
  if command -v apt >/dev/null 2>&1; then
    sudo apt update && sudo apt install -y python3 python3-venv python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm python
  else
    echo "Could not detect your package manager. Please install python3 (3.9+) yourself."
    read -n 1 -s -r -p "Press any key to close."
    exit 1
  fi
  is_compatible python3 && PY="python3"
fi

if [ -z "$PY" ]; then
  echo "Still no compatible Python. Please install Python 3.9+ and re-run."
  read -n 1 -s -r -p "Press any key to close."
  exit 1
fi

echo "Using Python: $PY ($($PY --version 2>&1))"

# ---- 3. Create the virtual environment (the "container") -------------
if [ ! -x "$APPDIR/.venv/bin/python" ]; then
  echo "Creating virtual environment..."
  if ! "$PY" -m venv "$APPDIR/.venv"; then
    echo "Could not create venv. On Debian/Ubuntu run: sudo apt install python3-venv"
    read -n 1 -s -r -p "Press any key to close."
    exit 1
  fi
fi
VENVPY="$APPDIR/.venv/bin/python"

# ---- 4. Install required packages (only the first time) --------------
if [ ! -f "$APPDIR/.venv/.installed" ]; then
  echo "Installing required packages (one-time)..."
  "$VENVPY" -m pip install --upgrade pip
  if ! "$VENVPY" -m pip install -r "$APPDIR/requirements.txt"; then
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
