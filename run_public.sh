#!/usr/bin/env bash
# Project Kairos — serve PUBLICLY via a Cloudflare Quick Tunnel.
#
# Runs the full app (Odin + Claude) on THIS always-on host and exposes it at an instant
# https://<random>.trycloudflare.com URL that ANYONE can open — no account, no domain, no
# port-forwarding, and it keeps working even when other machines (your laptop) are off,
# because it runs on this host.
#
#   Requirements on this host (see HOSTING.md):
#     - the app set up + working locally (venv, `claude` /login, `odin auth status` = true)
#     - cloudflared installed:  brew install cloudflared   (mac)   or see HOSTING.md (linux)
#
#   IMPORTANT: a public link should NOT be open. Set an access passcode first:
#     export KAIROS_APP_PASSWORD="choose-a-passcode"
#
#   Usage:  ./run_public.sh
#
# The Quick Tunnel URL CHANGES every restart. For a STABLE custom URL (and SSO auth),
# use a Cloudflare *named* tunnel — see HOSTING.md → "Stable public URL".
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8501}"
PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"

command -v cloudflared >/dev/null 2>&1 || {
  echo "ERROR: cloudflared is not installed. Install it, then re-run:"
  echo "  mac:   brew install cloudflared"
  echo "  linux: see HOSTING.md → 'Install cloudflared'"; exit 1; }

# Refuse-to-be-silent about an open public link.
have_pw=0
[ -n "${KAIROS_APP_PASSWORD:-}" ] && have_pw=1
grep -q '^KAIROS_APP_PASSWORD *= *"[^"]\+"' .streamlit/secrets.toml 2>/dev/null && have_pw=1
if [ "$have_pw" = "0" ]; then
  echo "############################################################"
  echo "# WARNING: no access passcode set — this PUBLIC link will   #"
  echo "# be open to anyone with the URL. Set one and re-run:       #"
  echo "#   export KAIROS_APP_PASSWORD='something'                  #"
  echo "# Continuing in 6s (Ctrl-C to abort)…                       #"
  echo "############################################################"
  sleep 6
fi

export KAIROS_MODEL_BACKEND="${KAIROS_MODEL_BACKEND:-cli}"

# App listens on localhost only — the tunnel reaches it; nothing is exposed on the LAN.
"$PY" -m streamlit run app.py \
  --server.address 127.0.0.1 --server.port "$PORT" --server.headless true &
APP_PID=$!
trap 'kill $APP_PID 2>/dev/null || true' EXIT INT TERM

printf "Waiting for the app to start"
for _ in $(seq 1 40); do
  curl -sf "http://127.0.0.1:${PORT}/_stcore/health" >/dev/null 2>&1 && break
  printf "."; sleep 1
done
echo

echo "==> Opening the public tunnel. Your shareable https URL is printed below:"
echo
exec cloudflared tunnel --url "http://127.0.0.1:${PORT}"
