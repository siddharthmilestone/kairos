# Install Project Kairos (Windows and Mac)

Kairos runs **on your computer**. Double-click to open it. The first time, it
installs Python 3.9+ (if needed) and the app. After that, the same click starts it.

Generation uses **your** Claude login. Grounding uses **your** Odin login.

---

## What to share with teammates

Share the **whole `kairos` project folder** — not one file, and not a single
subfolder.

`Kairos.bat`, `Kairos.command`, and `Kairos.exe` only **start** the app. They
need `app.py`, `lib/`, `prompts/`, `scripts/`, `requirements.txt`, and
`.streamlit/` sitting next to them.

### Easy way

Zip the `kairos` folder (or send a `git clone` link) and give people that.

**Leave out** these if they are on your machine (each person recreates them):

| Do not copy | Why |
|---|---|
| `.venv/` | Built on their PC by the first run |
| `data/_cache/` | Their own cache |
| `build/`, `dist/`, `Kairos.exe` | Windows build leftovers (optional) |
| `__pycache__/` | Junk |

A `git clone` already skips those (they are gitignored). That is the cleanest share.

### Do not send

- **Only** `Kairos.exe` or **only** `Kairos.bat` — it will not run.
- **Only** `lib/` or `scripts/` — the app will not start.

---

## 1. Put the folder on the computer

Copy the full `kairos` folder (from the zip or clone).
Do not move the start file out of that folder.

## 2. Sign in once (Odin + Claude)

These are your accounts. The app cannot sign in for you.

```text
odin auth login          ← finish MFA in the browser
claude                   ← then type /login
```

Claude **Desktop** is not enough. You need the **Claude Code CLI** (`claude`).

Stay on the office network or VPN so Odin can reach its backend.

## 3. Start Kairos

| Windows | Mac |
|---|---|
| Double-click **`Kairos.bat`** | First time: `chmod +x Kairos.command setup.sh run.sh scripts/ensure_python.sh` |
| | Then double-click **`Kairos.command`** |

The first run may take a few minutes (Python + packages + Chromium).
Your browser opens **http://localhost:8501**.

Keep the console / Terminal window open while you work. Close it to quit.

`setup.bat` / `./setup.sh` are optional — use them only if you want to install
without starting the app.

---

## First screen

**Create New Content** and **Optimize An Existing Page**.

- Sidebar **Odin: connected** — graph login is working.
- Sidebar **Engine: Claude CLI** — generation will use your Claude login.

If Odin is not connected: run `odin auth login`, then **Recheck Odin** in
**System & settings**, or pick **Non-Odin Business**.

---

## If something fails

| Symptom | What to do |
|---|---|
| Windows asks for permission while installing Python | Accept / Yes. That is the one-time Python install. |
| Mac asks for a password | That is the official Python installer. Enter your Mac password. |
| Python still missing after install | Close the window, open a **new** one, double-click Kairos again. |
| Port already in use | Close the other Kairos window, or set `PORT=8502`. |
| Odin: sign-in needed | `odin auth login`, then Recheck Odin. |
| Could not reach Odin / WinError 193 | Fixed in this build: Kairos uses `odin.ps1` on Windows and `odin` on Mac. Click **Recheck Odin**. |
| Engine red / generation fails | `claude` then `/login`. |
| Mac: permission denied | `chmod +x Kairos.command setup.sh run.sh scripts/ensure_python.sh` |
| Mac: unidentified developer | Right-click **Kairos.command** → **Open** → **Open**. |
| “app.py not found” | You copied only the starter file. Copy the **whole folder**. |

You do **not** need a `.streamlit/secrets.toml` file.

---

## What this is not

- Not a website on Azure.
- Not your teammate’s Claude Desktop.
- Each person uses **their** Odin and Claude on **their** machine.
