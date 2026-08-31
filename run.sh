#!/usr/bin/env bash
# Launch the Project Kairos.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x "./.venv/bin/streamlit" ]; then
  echo "✖ .venv not found. Run ./setup.sh first." >&2
  exit 1
fi

# Make sure the odin and claude CLIs are reachable from inside the app.
export PATH="$HOME/.odin/bin:$HOME/.local/bin:$PATH"

PORT="${PORT:-8501}"
echo "▶ Starting Project Kairos on http://localhost:${PORT}"
echo "  (Tip: choose a 'Non-Odin Business' to test without the internal Odin tool.)"
exec ./.venv/bin/streamlit run app.py \
  --server.address localhost --server.port "${PORT}" --server.headless true "$@"
