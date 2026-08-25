#!/usr/bin/env bash
# Project Kairos — run the app as an internal shared server.
#
# Serves the app on 0.0.0.0:<PORT> so teammates on the same network can open it at
# http://<this-machine-ip>:<PORT>. Keeps the FULL feature set (Odin + Claude CLI),
# because it runs on a machine where you have logged into both.
#
#   Prerequisites on THIS machine (see HOSTING.md):
#     - Python 3.9+ venv at ./.venv with requirements installed
#     - Claude Code CLI logged in     (run: claude   then  /login)
#     - Odin CLI authenticated        (run: odin auth login  → odin auth status)
#     - (optional) an access passcode: export KAIROS_APP_PASSWORD="something"
#
#   Usage:
#     ./run_server.sh              # serves on port 8501
#     PORT=9000 ./run_server.sh    # custom port
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8501}"
PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"   # fall back to system python if no venv

# Full-feature (local CLI) backend by default. Set KAIROS_MODEL_BACKEND=api to use the
# Anthropic API instead (needs ANTHROPIC_API_KEY) — not required for internal hosting.
export KAIROS_MODEL_BACKEND="${KAIROS_MODEL_BACKEND:-cli}"

echo "Project Kairos → http://$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo localhost):${PORT}"
echo "(share that link with teammates on the same network; Ctrl-C to stop)"

exec "$PY" -m streamlit run app.py \
  --server.address 0.0.0.0 \
  --server.port "$PORT" \
  --server.headless true
