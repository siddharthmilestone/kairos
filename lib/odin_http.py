"""Odin backend over plain HTTP — no `odin` CLI, no bun, no local auth cache.

The CLI is a bun script that shells out per call and reads a device-code session
from ~/.config/odin. Neither survives a serverless deploy, so this speaks the same
wire protocol directly: POST {BACKEND}/api/tools/{tool} with a bearer token, and
scope/kind injected into the payload as _context_scope / _kind.

Auth is a service token in ODIN_ACCESS_TOKEN. The CLI documents this as the
CI/service path that skips Entra entirely.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

BACKEND = (os.environ.get("ODIN_BACKEND_URL") or "https://odin-staging.milestonedev.info").rstrip("/")
USER_AGENT = "kairos-web/1.0"

REAUTH_MESSAGE = (
    "Kairos cannot reach your knowledge base — its access token is missing or expired. "
    "Set ODIN_ACCESS_TOKEN in the deployment settings."
)


class OdinAuthError(RuntimeError):
    """Raised when the backend rejects our credentials."""


def _token() -> str:
    return os.environ.get("ODIN_ACCESS_TOKEN") or os.environ.get("ODIN_API_TOKEN") or ""


def call(tool: str, payload: dict[str, Any] | None = None, *, scope: str | None = None,
         kind: str | None = None, timeout: int = 120) -> Any:
    """Invoke one backend tool. Returns the parsed `data` payload."""
    body = dict(payload or {})
    scope = scope or os.environ.get("ODIN_CONTEXT_SCOPE") or ""
    kind = kind or os.environ.get("ODIN_KIND") or ""
    if scope and "_context_scope" not in body:
        body["_context_scope"] = scope
    if kind and "_kind" not in body:
        body["_kind"] = kind

    token = _token()
    if not token:
        raise OdinAuthError(REAUTH_MESSAGE)

    req = urllib.request.Request(
        f"{BACKEND}/api/tools/{tool}",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            parsed = json.loads(res.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        if e.code in (401, 403):
            raise OdinAuthError(REAUTH_MESSAGE) from e
        raise RuntimeError(f"odin {tool} failed ({e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach the knowledge base at {BACKEND}: {e.reason}") from e

    if isinstance(parsed, dict) and parsed.get("error"):
        msg = str(parsed.get("message") or parsed["error"])
        if "401" in msg or "unauthor" in msg.lower():
            raise OdinAuthError(REAUTH_MESSAGE)
        raise RuntimeError(f"odin {tool}: {msg}")
    return parsed.get("data", parsed) if isinstance(parsed, dict) else parsed


def auth_status() -> dict[str, Any]:
    """Cheap credential probe used by the health endpoint."""
    if not _token():
        return {"authenticated": False, "reason": "ODIN_ACCESS_TOKEN not set"}
    try:
        call("get_graph_summary", {}, timeout=20)
        return {"authenticated": True, "method": "service_token", "backend": BACKEND}
    except OdinAuthError as e:
        return {"authenticated": False, "reason": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"authenticated": False, "reason": str(e)[:200]}
