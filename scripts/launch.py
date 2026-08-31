"""Cross-platform Kairos launcher (Windows + macOS).

  python scripts/launch.py --setup   # first-time: venv, deps, Playwright Chromium
  python scripts/launch.py           # start the desktop app (opens the browser)

When frozen as Kairos.exe, the project root is the folder that contains the exe
and app.py — keep them together.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PORT = os.environ.get("PORT", "8501")
URL = f"http://localhost:{PORT}"


def root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def venv_python(repo: Path) -> Path:
    if os.name == "nt":
        return repo / ".venv" / "Scripts" / "python.exe"
    return repo / ".venv" / "bin" / "python"


def _is_39(cmd: list[str]) -> bool:
    try:
        r = subprocess.run(
            cmd + ["-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"],
            capture_output=True, timeout=20,
        )
        return r.returncode == 0
    except Exception:
        return False


def which_python() -> str:
    """System Python 3.9+ used only to create the venv."""
    if not getattr(sys, "frozen", False) and sys.version_info >= (3, 9):
        return sys.executable

    if os.name == "nt":
        py = shutil.which("py")
        if py and _is_39([py, "-3"]):
            return py
        for name in ("python", "python3"):
            hit = shutil.which(name)
            if hit and _is_39([hit]):
                return hit
    else:
        for name in ("python3", "python"):
            hit = shutil.which(name)
            if hit and _is_39([hit]):
                return hit

    sys.exit(
        "Python 3.9+ is required.\n"
        "  Windows: double-click Kairos.bat — it will install Python if needed.\n"
        "  Mac:     double-click Kairos.command — it will install Python if needed."
    )


def prepend_cli_path() -> None:
    home = Path.home()
    extra = [
        home / ".odin" / "bin",
        home / ".local" / "bin",
    ]
    if os.name == "nt":
        extra.append(home / "AppData" / "Local" / "Programs" / "claude")
    prefix = os.pathsep.join(str(p) for p in extra if p.is_dir())
    if prefix:
        os.environ["PATH"] = prefix + os.pathsep + os.environ.get("PATH", "")


def have_cli(name: str, extra: list[Path]) -> bool:
    if shutil.which(name):
        return True
    return any(p.is_file() for p in extra)


def print_cli_status() -> None:
    home = Path.home()
    odin_ok = have_cli("odin", [home / ".odin" / "bin" / "odin", home / ".odin" / "bin" / "odin.exe"])
    claude_ok = have_cli(
        "claude",
        [
            home / ".local" / "bin" / "claude",
            home / ".local" / "bin" / "claude.exe",
        ],
    )
    print("  Odin CLI:   " + ("found" if odin_ok else "NOT FOUND — install, then run:  odin auth login"))
    print("  Claude CLI: " + ("found" if claude_ok else "NOT FOUND — install, then run:  claude  (type /login)"))
    if not odin_ok or not claude_ok:
        print("  See INSTALL.md for Windows and Mac install steps.")


def run(cmd: list[str], **kwargs) -> None:
    print("  $", " ".join(str(c) for c in cmd))
    subprocess.check_call(cmd, **kwargs)


def setup(repo: Path) -> None:
    print("Project Kairos — first-time setup")
    print("Project folder:", repo)
    py = which_python()
    if os.name == "nt" and Path(py).name.lower() == "py.exe":
        ver_cmd = [py, "-3", "--version"]
        venv_cmd = [py, "-3", "-m", "venv", str(repo / ".venv")]
    else:
        ver_cmd = [py, "--version"]
        venv_cmd = [py, "-m", "venv", str(repo / ".venv")]
    run(ver_cmd)

    print("Creating virtualenv (.venv)…")
    run(venv_cmd)

    vpy = venv_python(repo)
    if not vpy.is_file():
        sys.exit(f"Virtualenv was not created at {vpy}")

    print("Installing Python packages (a few minutes)…")
    run([str(vpy), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(vpy), "-m", "pip", "install", "-r", str(repo / "requirements.txt")])

    print("Installing Playwright Chromium (Optimize-page crawl)…")
    try:
        run([str(vpy), "-m", "playwright", "install", "chromium"])
    except subprocess.CalledProcessError:
        print("  Warning: Chromium install failed — Optimize will fall back to a plain HTTP fetch.")

    print("Verifying imports…")
    run(
        [
            str(vpy),
            "-c",
            "import streamlit, docx, pypdf, markdown2, xhtml2pdf, bs4, lxml, playwright, trafilatura; "
            "print('  python deps OK — streamlit', streamlit.__version__)",
        ]
    )
    prepend_cli_path()
    print_cli_status()
    print()
    print("Setup complete. Starting the app next (or double-click Kairos again).")


def start(repo: Path) -> None:
    vpy = venv_python(repo)
    if not vpy.is_file():
        print("No virtualenv yet. Running first-time setup…")
        setup(repo)
        vpy = venv_python(repo)
    if not (repo / "app.py").is_file():
        sys.exit(f"app.py not found in {repo}. Put the launcher next to the Kairos project folder.")

    prepend_cli_path()
    print("Project Kairos")
    print(f"  Opening {URL}")
    print("  Keep this window open while you use the app. Close it to quit.")
    print_cli_status()
    print()

    env = dict(os.environ)
    args = [
        str(vpy),
        "-m",
        "streamlit",
        "run",
        str(repo / "app.py"),
        "--server.port",
        PORT,
        "--server.address",
        "127.0.0.1",
        "--server.headless",
        "false",
        "--browser.gatherUsageStats",
        "false",
    ]
    os.chdir(repo)
    raise SystemExit(subprocess.call(args, env=env))


def main() -> None:
    repo = root()
    if "--setup" in sys.argv:
        setup(repo)
        return
    start(repo)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode or 1)
