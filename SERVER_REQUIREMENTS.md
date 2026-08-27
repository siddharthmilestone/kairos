# Project Kairos — server requirements (for IT / infra)

A Python **Streamlit** web app. It generates content through the **Claude Code CLI** and grounds
it in **Odin** (an internal Milestone memory‑graph CLI). Both are command‑line tools that must be
**installed and logged in on the host**, which is the main thing that shapes where it can run.

> **Why not a generic public cloud (Streamlit Cloud, Render, etc.)?** Odin authenticates to an
> internal Milestone backend (Entra device‑code) and only works from inside the corporate
> network; the Claude CLI uses an interactive login. Neither can run on outside cloud. So Kairos
> must run on a **machine inside Milestone's network**, and we expose it publicly with an
> **outbound‑only Cloudflare Tunnel** (no inbound ports).

---

## 1. Host machine

| | Minimum | Recommended |
|---|---|---|
| OS | Linux (Ubuntu 22.04+/Debian) or macOS | Ubuntu 22.04 LTS |
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Disk | 5 GB free | 10 GB free |
| Uptime | **Always‑on / 24×7** (VM, Mac mini, or spare box — **not** a laptop) | |
| Arch | x86‑64 or ARM64 | |

A small always‑on VM is ideal. One host serves the whole team.

## 2. Network (the important part)

- **Must sit inside Milestone's network / VPN** so the **Odin CLI can reach its backend and
  authenticate**. This is a hard requirement — without it, the core "grounded in Odin" feature
  does not work.
- **Outbound HTTPS (443)** to: Anthropic API (Claude), the Odin backend, Cloudflare
  (`*.cloudflare.com`, `*.argotunnel.com`), GitHub, and PyPI. Standard egress.
- **No inbound ports required** if we use the Cloudflare Tunnel for the public URL (the tunnel
  dials outbound). If instead you want it LAN‑only, open inbound TCP on the app port (default
  `8501`) and skip the tunnel.

## 3. Software to install on the host

- **Python 3.9+** (3.11 recommended) with `pip` and `venv`.
- **Git** (to deploy + update).
- **Node‑free** — no Node.js needed.
- **Chromium system libraries** for the page‑crawl feature — installed via
  `playwright install --with-deps chromium` (pulls the needed OS libs on Linux).
- **Claude Code CLI** — installed and **logged in on the host** (interactive, once). Uses a
  Claude account/subscription; all app users share this one login. *(Optional alternative: run
  on the Anthropic API instead by setting `ANTHROPIC_API_KEY` — a paid metered key.)*
- **Odin CLI** — installed and **authenticated on the host** (`odin auth login`, device‑code).
  Requires an identity that has Odin access.
- **cloudflared** — only for the public URL (Cloudflare Tunnel).

## 4. Accounts / credentials IT must provision

Kairos itself stores **no secrets in the repo**. What the host needs is:

1. A **Claude login** on the host (or an `ANTHROPIC_API_KEY`).
2. An **Odin‑authorized identity** logged in on the host (Entra device‑code).
3. *(For a stable public URL)* a **Cloudflare account + a domain on Cloudflare** to run a named
   tunnel (e.g. `kairos.milestoneinternet.com`). A no‑account "quick tunnel" also works but gives
   a random URL that changes on restart.

These logins are done **once, interactively, on the host** and persist. If a session expires,
someone re‑runs the login on the host (the app shows engine/Odin status in its sidebar).

## 5. Deploy (summary — full steps in HOSTING.md)

```bash
git clone https://github.com/siddharthmilestone/kairos.git
cd kairos
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install --with-deps chromium
claude            # then /login   (Claude CLI)
odin auth login   # then confirm: odin auth status
export KAIROS_APP_PASSWORD="a-team-passcode"     # required for a public link
./run_public.sh   # app + Cloudflare quick tunnel → prints a public https URL
```

Run it as a service (auto‑restart, start on boot) using the provided systemd units
`deploy/kairos.service` and `deploy/cloudflared.service` (see HOSTING.md §6).

## 6. Security

- The app has a built‑in **passcode gate** (`KAIROS_APP_PASSWORD`) — set it for any public link.
- For real sign‑in, put **Cloudflare Access** (Zero Trust, free up to 50 users, email‑OTP or
  Google/Entra SSO) in front of the tunnel URL.
- **Shared session:** everyone who can reach the app generates under the host's single Claude +
  Odin login — keep the audience controlled.
- Keep the box on the internal network / behind the tunnel; do not port‑forward it raw to the
  internet.

## 7. Operations

- **Keep‑alive:** systemd services restart on crash and start on boot.
- **Concurrency:** each generation spawns a `claude -p` process; a handful of simultaneous users
  is fine — size CPU/RAM up for heavier load.
- **Storage:** results cache to `data/_cache` on the host (safe to delete; regenerates).
- **Updates:** `git pull && .venv/bin/pip install -r requirements.txt && systemctl restart kairos`.
- **Logins expiring:** if Claude or Odin auth lapses, generation/grounding fails app‑wide until
  someone re‑logs in on the host.

---

**TL;DR for IT:** one always‑on Linux VM (4 vCPU / 8 GB / 10 GB) **on the internal network**,
Python 3.11, outbound 443, Chromium libs, the Claude + Odin CLIs logged in on the box, and
`cloudflared` for an outbound‑only public URL. No inbound firewall changes, no database, no
secrets in the repo.
