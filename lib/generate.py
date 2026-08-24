"""Run the assembled prompt through the Claude Code CLI in headless mode.

Uses the user's existing `claude` login — no API key handled here.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time

HOME = os.path.expanduser("~")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or f"{HOME}/.local/bin/claude"

# transient backend/network failures worth retrying (the socket sometimes drops mid-call)
_TRANSIENT_SIGNS = (
    "socket connection was closed", "socket hang up", "econnreset", "connection reset",
    "etimedout", "epipe", "fetch failed", "network", "connection error", "connection closed",
    "overloaded", "rate limit", "too many requests", "429", "500", "502", "503", "504",
    "internal server error", "service unavailable", "temporarily unavailable", "timeout",
)


def _is_transient(text: str) -> bool:
    t = (text or "").lower()
    return any(s in t for s in _TRANSIENT_SIGNS)


def generate(prompt: str, model: str = "opus", timeout: int = 900,
             allow_tools: bool = True) -> str:
    """Send `prompt` to `claude -p` and return the text response.

    The prompt is fully self-contained (grounding already injected). Set
    `allow_tools=False` for steps that are graph/artifact-grounded and must NOT
    browse the web (PR calendar, topic planning, brief Q&A) — this passes
    `--tools ""` to disable all tools, which makes generation fast and bounded
    (uncontrolled web-browsing under bypassPermissions was making these steps
    run 15–20+ minutes). Keep `allow_tools=True` where live web research is the
    point (content draft, fan-out SERP, optimize plan).
    """
    env = dict(os.environ)
    env["PATH"] = f"{HOME}/.local/bin:" + env.get("PATH", "")
    args = [
        CLAUDE_BIN, "-p",
        "--output-format", "text",
        "--model", model,
        "--permission-mode", "bypassPermissions",
    ]
    if not allow_tools:
        args += ["--tools", ""]  # disable all tools → pure, fast, bounded generation

    # Retry transient backend/network failures (e.g. "socket connection was closed") with
    # backoff — one dropped socket shouldn't fail a whole generation step. A hard timeout is
    # NOT retried (it already consumed the full budget). Non-transient errors fail fast.
    attempts = 3
    last_err = ""
    for attempt in range(attempts):
        try:
            proc = subprocess.run(args, input=prompt, env=env, capture_output=True,
                                  text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"claude -p timed out after {timeout}s.") from e
        if proc.returncode == 0:
            out = proc.stdout.strip()
            if out:
                return out
            last_err = "claude -p returned empty output."
        else:
            last_err = (proc.stderr or proc.stdout).strip()[:800]
            if not _is_transient(last_err):
                raise RuntimeError(f"claude -p failed (exit {proc.returncode}): {last_err}")
        if attempt < attempts - 1:
            time.sleep(min(20, 4 * (attempt + 1)))  # 4s, 8s
    raise RuntimeError(f"claude -p failed after {attempts} attempts: {last_err}")
