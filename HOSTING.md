# Hosting Project Kairos — a public URL, laptop-off, with Odin intact

This runs the **full** app — Odin memory‑graph grounding **and** the Claude CLI — on one
**always‑on machine you control**, and exposes it at a **public URL anyone can open**, even
when your laptop is off, via a **Cloudflare Tunnel**.

> Why this shape? Odin is an internal CLI (device‑code auth to an internal backend) and the
> app generates through your local `claude` login. Neither can run on public cloud (Streamlit
> Cloud, Render, …). So the app runs on an always‑on host *inside* your network, and a tunnel
> gives it a public address — you keep Odin **and** get a public link.

The setup is two layers: **(1)** get the app running on an always‑on host, then **(2)** put a
Cloudflare Tunnel in front for the public URL.

---

## 1. Pick the always‑on host

**Not your laptop** — a machine that stays on: a spare Mac/Linux box, a Mac mini, or an
internal VM. It must be able to run `odin` and `claude` (i.e. on/through Milestone's network).
Everyone who opens the public link uses **that machine's** Odin + Claude logins, so log in
once, there, as the user that will run the app.

## 2. One‑time setup on the host

```bash
git clone <your-repo-url> kairos   # or copy the folder onto the machine
cd kairos
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium      # for the Optimize-page crawl
```

Log both tools in **as the user that will run the server**:

```bash
claude            # then type: /login   (Claude Code CLI)
claude --version  # confirm it works

odin auth login   # device-code sign-in
odin auth status  # should show authenticated: true
```

## 3. (Recommended) set an access passcode

So the shared link isn't wide open. Pick any phrase; teammates enter it once:

```bash
export KAIROS_APP_PASSWORD="choose-a-team-passcode"
```

Or put it in `.streamlit/secrets.toml` (copy `.streamlit/secrets.toml.example`).
If you don't set one, the app is open to anyone who can reach the link.

## 4. Run it

```bash
./run_server.sh              # serves on port 8501
# or a custom port:
PORT=9000 ./run_server.sh
```

This confirms the app itself works on the host. `localhost:8501` works on the host; the
**public** URL comes from the tunnel in the next step (no firewall/port‑forwarding needed).

---

## 5. Make it public with a Cloudflare Tunnel

The tunnel dials **out** from the host to Cloudflare and serves the app at a public `https`
URL — no open inbound ports, no router config, works behind NAT/VPN.

### Install `cloudflared`
- **mac:** `brew install cloudflared`
- **linux (Debian/Ubuntu):**
  ```bash
  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
  ```

### Option A — instant public URL (Quick Tunnel, no account)
```bash
export KAIROS_APP_PASSWORD="choose-a-passcode"   # REQUIRED: the link is public
./run_public.sh
```
It starts the app and prints a public `https://<random>.trycloudflare.com` link — share it
with anyone. Works with your laptop off (it runs on this host). **Caveat:** the URL changes
every restart, and Quick Tunnels are best‑effort (fine for demos/sharing, not an SLA).

### Option B — stable custom URL (Named Tunnel, needs a Cloudflare account + a domain)
Gives a permanent URL like `https://kairos.yourcompany.com` that survives restarts, and lets
you add real sign‑in (below). One‑time:
```bash
cloudflared tunnel login                         # opens a browser; pick your Cloudflare domain
cloudflared tunnel create kairos                 # creates the tunnel + a credentials file
cloudflared tunnel route dns kairos kairos.yourcompany.com
```
Create `~/.cloudflared/config.yml`:
```yaml
tunnel: kairos
credentials-file: /home/<user>/.cloudflared/<TUNNEL-ID>.json
ingress:
  - hostname: kairos.yourcompany.com
    service: http://127.0.0.1:8501
  - service: http_status:404
```
Run it (and keep it alive as a service — see step 6):
```bash
cloudflared tunnel run kairos
```

### Lock it down (do this — it's public now)
- **Always** set `KAIROS_APP_PASSWORD` (the app's built‑in gate).
- **Better (Named Tunnel):** put **Cloudflare Access** (Zero Trust, free up to 50 users) in
  front of `kairos.yourcompany.com` — email OTP or SSO (Google/Entra), so only approved people
  reach the app at all. Cloudflare dashboard → Zero Trust → Access → Applications.
- Everyone shares the host's single Odin + Claude session, so anyone with access can generate
  under those credentials — keep the audience controlled.

## 6. Keep it running 24/7 (so the public URL is always up)

- **Quick (Mac/Linux):** run each in its own `tmux`/`screen` so they survive your SSH session:
  ```bash
  tmux new -s kairos  './run_public.sh'   # app + Quick Tunnel together
  # (detach: Ctrl-b then d · reattach: tmux attach -t kairos)
  ```
- **Linux services (auto‑restart + start on boot) — recommended for a stable URL:** edit the
  paths/user in the two unit files, then install both:
  ```bash
  # 1) the app
  sudo cp deploy/kairos.service     /etc/systemd/system/kairos.service
  # 2) the named tunnel (Option B)
  sudo cp deploy/cloudflared.service /etc/systemd/system/cloudflared-kairos.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now kairos cloudflared-kairos
  journalctl -u kairos -u cloudflared-kairos -f   # live logs
  ```
  The app listens on `127.0.0.1:8501`; the tunnel serves it publicly. Both restart on crash and
  start on boot, so the public URL stays up without anyone logged in.

## 7. Updating

```bash
git pull                                   # or re-copy the folder
.venv/bin/pip install -r requirements.txt  # if deps changed
sudo systemctl restart kairos              # (tunnel keeps running)
```

---

## Good to know

- **Shared logins.** Every visitor generates through the host's single Claude + Odin session.
  That's intended for internal sharing. If the Claude login expires, generation fails app‑wide
  until you re‑run `claude` → `/login` on the host (the sidebar **System & settings** shows engine
  status; the app also falls back to the Anthropic API if `ANTHROPIC_API_KEY` is set).
- **Concurrency.** Each generation spawns a `claude -p` process. A handful of simultaneous users
  is fine; for heavy load, run on a bigger box.
- **Cache.** Results cache to `data/_cache` on the host, so repeat runs and demos are instant.
  Pre‑warm popular businesses with `.venv/bin/python scripts/prewarm.py`.
- **No public exposure.** Keep the port on your LAN/VPN. Don't forward it to the open internet
  without putting real authentication in front of it — the passcode gate is a light guard, not
  enterprise auth.
