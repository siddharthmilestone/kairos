#!/usr/bin/env bash
# Project Kairos — first-time setup (Mac / Linux). Installs Python 3.9+ if needed.
set -euo pipefail
cd "$(dirname "$0")"
PY="$(bash scripts/ensure_python.sh)"
exec "$PY" scripts/launch.py --setup
