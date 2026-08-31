#!/usr/bin/env bash
# Project Kairos — one-time setup.
# Creates a local virtualenv and installs Python dependencies.
#
# Prereqs:
#   - python3 (3.9+)
#   - the Claude Code CLI, logged in  (REQUIRED — this is what generates content)
#   - the `odin` CLI                  (OPTIONAL — internal Milestone tool; without it the app
#                                       runs in public-web mode, which is what testers use)
set -euo pipefail
cd "$(dirname "$0")"

echo "▶ Checking Python…"
if ! command -v python3 >/dev/null 2>&1; then
  echo "✖ python3 not found. Install Python 3.9+ and re-run." >&2
  exit 1
fi
python3 --version

echo "▶ Creating virtualenv (.venv)…"
python3 -m venv .venv

echo "▶ Upgrading pip…"
./.venv/bin/python -m pip install --quiet --upgrade pip

echo "▶ Installing dependencies…"
./.venv/bin/pip install --quiet -r requirements.txt

echo "▶ Installing headless browser for the Optimize branch (Playwright Chromium)…"
./.venv/bin/python -m playwright install chromium || \
  echo "  ⚠ Chromium install failed — the Optimize crawl will fall back to plain HTTP fetch."

echo "▶ Verifying imports…"
./.venv/bin/python -c "import streamlit, docx, pypdf, markdown2, xhtml2pdf, bs4, lxml, playwright, trafilatura; print('  python deps OK — streamlit', streamlit.__version__)"

echo "▶ Checking external CLIs…"
if command -v claude >/dev/null 2>&1 || [ -x "$HOME/.local/bin/claude" ]; then
  echo "  ✓ claude (Claude Code) CLI: found"
  claude_ok=1
else
  echo "  ✖ claude (Claude Code) CLI NOT found — REQUIRED. Install it and run:  claude  then  /login"
  echo "    Install: https://docs.claude.com/claude-code"
  claude_ok=0
fi
if command -v odin >/dev/null 2>&1 || [ -x "$HOME/.odin/bin/odin" ]; then
  echo "  ✓ odin CLI: found (optional)"
else
  echo "  · odin CLI: not found (optional) — the app will run in public-web mode. Testers don't need it."
fi

echo ""
echo "✅ Setup complete."
if [ "${claude_ok:-0}" = "0" ]; then
  echo "⚠ Before running, install the Claude Code CLI and log in:  claude  →  /login"
fi
echo "Start the app with:  ./run.sh   (opens http://localhost:8501)"
echo "In the app, choose a 'Non-Odin Business' and enter any business name + website to test."
