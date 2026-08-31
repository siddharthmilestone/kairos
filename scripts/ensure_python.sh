#!/usr/bin/env bash
# Find Python 3.9+ or install it (Mac / Linux). Prints the interpreter path on stdout.
set -euo pipefail

msg() { echo "$@" >&2; }

ok() {
  "$1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1
}

find_py() {
  local c p
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && ok "$c"; then
      command -v "$c"
      return 0
    fi
  done
  for p in \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
    "$HOME/.local/bin/python3"
  do
    if [ -x "$p" ] && ok "$p"; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

install_py() {
  msg ""
  msg "Python 3.9+ was not found. Installing Python (one-time)…"
  if command -v brew >/dev/null 2>&1; then
    msg "Using Homebrew…"
    brew install python@3.12 2>/dev/null || brew install python
    return 0
  fi
  msg "Homebrew not found. Downloading the official Python 3.12 installer."
  msg "macOS may ask for your password."
  local pkg="/tmp/kairos-python-3.12.10-macos11.pkg"
  curl -fsSL -o "$pkg" "https://www.python.org/ftp/python/3.12.10/python-3.12.10-macos11.pkg"
  sudo installer -pkg "$pkg" -target /
}

if PY="$(find_py)"; then
  msg "Using Python: $PY"
  echo "$PY"
  exit 0
fi

install_py
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-}"

if PY="$(find_py)"; then
  msg "Using Python: $PY"
  echo "$PY"
  exit 0
fi

msg "Python was installed but this window cannot see it yet."
msg "Quit Terminal, open it again, and double-click Kairos.command."
exit 1
