# Quick start — run Project Kairos on your own machine

A local content‑intelligence app you run yourself. It generates through **your own Claude
login**, so each tester uses their own Claude account. **No Odin needed** — Odin is an
internal Milestone tool; without it the app runs in **public‑web mode**, which is exactly what
testing uses.

## What you need
- **Python 3.9+** (`python3 --version`)
- **Git**
- The **Claude Code CLI**, installed and logged in with your Claude account
  ([install docs](https://docs.claude.com/claude-code)). This is what powers generation.
- macOS or Linux. **Windows:** use **WSL** (Ubuntu).

> You do **not** need Odin, an API key, or any config file to test.

## Set up (about 3 minutes)
```bash
git clone https://github.com/siddharthmilestone/kairos.git
cd kairos
./setup.sh          # creates a venv, installs deps + a headless browser
```

Make sure Claude is logged in (once):
```bash
claude              # then type: /login
claude --version    # confirm it works
```

## Run it
```bash
./run.sh            # opens http://localhost:8501
```

## Test it (2 minutes)
1. **Objective:** pick **Create New Content**.
2. **Format & Language:** e.g. *Blog Article*, *English*.
3. **Business:** choose the **Non‑Odin Business** tile, then enter any real business —
   a **name**, a **location or brand**, and its **website URL** (e.g. `The Beach House, Goa,
   https://…`). Everything is grounded from the public web and cited.
4. Walk the wizard — **Preferences → Choose Topic → Query Fan‑Out → Topic Q&A → Call to
   Action → Generate → Review**. The Generate step runs on your Claude login (a few minutes).
5. In **Review**, read the publish‑ready content, the pre‑flight quality gates, the JSON‑LD in
   the SEO/Ops tab, and download the PDF/Word/Markdown or the enterprise report.

## Notes
- **It uses your Claude account.** Generation shells out to `claude -p`, so an active Claude
  login/subscription is required, and usage counts against your account. If a run says the login
  expired, run `claude` → `/login` again.
- **Odin businesses won't work** off Milestone's network — that's expected; use Non‑Odin.
- **Results cache** to `data/_cache` locally, so repeat runs are instant. Safe to delete.
- **Stuck?** `./setup.sh` re‑runs safely. Full hosting/ops details are in
  [`HOSTING.md`](HOSTING.md) and [`SERVER_REQUIREMENTS.md`](SERVER_REQUIREMENTS.md).
