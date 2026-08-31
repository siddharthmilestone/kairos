#!/bin/bash
# Double-click in Finder (Mac). Keep this window open while you use Kairos.
cd "$(dirname "$0")"
export PATH="$HOME/.odin/bin:$HOME/.local/bin:$PATH"
chmod +x setup.sh run.sh scripts/ensure_python.sh scripts/launch.py 2>/dev/null || true

if [ -x "./.venv/bin/python" ] && "./.venv/bin/python" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
  exec "./.venv/bin/python" scripts/launch.py
fi

echo "Checking Python…"
if ! PY="$(bash scripts/ensure_python.sh)"; then
  read -r -p "Press Enter to close…"
  exit 1
fi
exec "$PY" scripts/launch.py
