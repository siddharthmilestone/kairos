# Hosting Project Kairos for your team (internal server)

This runs the **full** app — Odin memory‑graph grounding **and** the Claude CLI — on one
machine you control, and shares an internal link with teammates on the same network.

> Why not Streamlit Community Cloud? Odin is an internal CLI with device‑code auth and the
> app generates through your local `claude` login. Neither exists on Streamlit's public
> servers, so a cloud deploy would lose Odin (the core value). Self‑hosting keeps everything.

---

## 1. Pick the host machine

Any always‑on Mac or Linux box on your office network (or a VM/VPN teammates can reach).
Everyone who opens the link uses **that machine's** Odin + Claude logins, so log in once,
there, as the user that will run the app.

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

The script prints the shareable link, e.g. `http://10.0.12.34:8501`. Send that to your team
(they must be on the same network / VPN). `localhost` only works on the host itself.

**Firewall:** allow inbound TCP on the port (8501) on the host. On macOS you may get a
"accept incoming connections" prompt the first time — allow it.

## 5. Keep it running

- **Quick (Mac/Linux):** run inside `tmux` or `screen` so it survives your SSH session:
  ```bash
  tmux new -s kairos './run_server.sh'   # detach with Ctrl-b then d; reattach: tmux attach -t kairos
  ```
- **Linux service (auto‑restart + start on boot):** edit paths/user in
  [`deploy/kairos.service`](deploy/kairos.service), then:
  ```bash
  sudo cp deploy/kairos.service /etc/systemd/system/kairos.service
  sudo systemctl daemon-reload && sudo systemctl enable --now kairos
  journalctl -u kairos -f      # live logs
  ```

## 6. Updating

```bash
git pull                                   # or re-copy the folder
.venv/bin/pip install -r requirements.txt  # if deps changed
# restart: Ctrl-C then ./run_server.sh   (or: sudo systemctl restart kairos)
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
