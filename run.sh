#!/usr/bin/env bash
# Launch Project Kairos in the browser (Mac / Linux).
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.odin/bin:$HOME/.local/bin:$PATH"

if [ -x "./.venv/bin/python" ] && "./.venv/bin/python" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
  exec "./.venv/bin/python" scripts/launch.py "$@"
fi

PY="$(bash scripts/ensure_python.sh)"
exec "$PY" scripts/launch.py "$@"
