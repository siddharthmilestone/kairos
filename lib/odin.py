"""Thin wrapper around the Odin CLI for the Project Kairos.

Everything goes through the local `odin` binary so we reuse the user's cached
Entra auth. No secrets handled here.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from functools import lru_cache
from typing import Any

HOME = os.path.expanduser("~")
_HOME_ODIN_BIN = os.path.join(HOME, ".odin", "bin")

REAUTH_MESSAGE = ("Odin session expired — your multi-factor sign-in needs refreshing. "
                  "Run `odin auth login` in a terminal, complete MFA, then reload this page.")
# Signatures in Odin CLI errors that mean "the token is stale, re-auth needed" (not "no data").
_REAUTH_SIGNS = ("entra_refresh_failed", "invalid_grant", "refresh_failed", "aadsts50078",
                 "multi-factor authentication has expired", "must refresh your multi-factor",
                 "odin auth login", "unauthorized", "401")


class OdinAuthError(RuntimeError):
    """Raised when Odin cannot serve because the user's auth/MFA has expired.

    Distinct from an empty result — this must surface, never be swallowed as
    'no grounding data'."""


def _is_reauth(text: str) -> bool:
    t = (text or "").lower()
    return any(s in t for s in _REAUTH_SIGNS)


def _looks_like_unix_script(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"#!"
    except OSError:
        return False


def _powershell() -> str:
    return shutil.which("pwsh") or shutil.which("powershell") or "powershell"


def _argv_for(path: str) -> list[str]:
    """Build the argv prefix that can actually execute this Odin wrapper on this OS.

    The Odin installer ships a Unix `odin` shell script and, on Windows, `odin.ps1`.
    Python's CreateProcess cannot run the shell script (WinError 193), so Windows
    must go through PowerShell + the .ps1. Mac/Linux exec the `odin` script as-is.
    Paths are resolved from $ODIN_BIN, PATH, or ~/.odin/bin — never a specific user.
    """
    path = os.path.expanduser(path)
    if os.name == "nt":
        ps1 = path if path.lower().endswith(".ps1") else os.path.join(
            os.path.dirname(path) or _HOME_ODIN_BIN, "odin.ps1")
        if (path.lower().endswith(".ps1") or _looks_like_unix_script(path)) and os.path.isfile(ps1):
            return [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1]
    return [path]


def _odin_argv() -> list[str]:
    override = (os.environ.get("ODIN_BIN") or "").strip()
    if override:
        return _argv_for(override)

    home_ps1 = os.path.join(_HOME_ODIN_BIN, "odin.ps1")
    home_sh = os.path.join(_HOME_ODIN_BIN, "odin")
    which = shutil.which("odin")

    if os.name == "nt":
        for candidate in (
            home_ps1,
            os.path.join(_HOME_ODIN_BIN, "odin.cmd"),
            os.path.join(_HOME_ODIN_BIN, "odin.exe"),
            which,
            home_sh,
        ):
            if candidate and os.path.isfile(candidate):
                return _argv_for(candidate)
        return _argv_for(home_ps1)

    if which:
        return _argv_for(which)
    return _argv_for(home_sh)


# Resolved wrapper path (for display / ODIN_BIN-style debugging). The real
# invocation is `_odin_argv()` and may be `powershell -File odin.ps1` on Windows.
ODIN_BIN = os.environ.get("ODIN_BIN") or shutil.which("odin") or (
    os.path.join(_HOME_ODIN_BIN, "odin.ps1") if os.name == "nt"
    else os.path.join(_HOME_ODIN_BIN, "odin")
)


def _env(scope: str | None = None, kind: str = "hospitality") -> dict[str, str]:
    env = dict(os.environ)
    extra = [
        _HOME_ODIN_BIN,
        os.path.join(HOME, ".bun", "bin"),
        os.path.join(HOME, ".local", "bin"),
    ]
    env["PATH"] = os.pathsep.join([p for p in extra if os.path.isdir(p)] + [env.get("PATH", "")])
    if scope:
        env["ODIN_CONTEXT_SCOPE"] = scope
    env["ODIN_KIND"] = kind
    return env


def _run(args: list[str], scope: str | None = None, kind: str = "hospitality",
         timeout: int = 90) -> str:
    proc = subprocess.run(
        [*_odin_argv(), *args],
        env=_env(scope, kind),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        if _is_reauth(err):
            raise OdinAuthError(REAUTH_MESSAGE)
        raise RuntimeError(f"odin {' '.join(args)} failed: {err}")
    return proc.stdout


def auth_status() -> dict[str, Any]:
    """Fast, cached identity check. NOTE: this reflects the stored token, which can
    report authenticated even after MFA has expired — use probe() to verify a live call."""
    try:
        return json.loads(_run(["auth", "status"], timeout=30))
    except OdinAuthError:
        return {"authenticated": False, "needs_reauth": True, "error": REAUTH_MESSAGE}
    except Exception as e:  # noqa: BLE001
        return {"authenticated": False, "error": str(e)}


def probe() -> dict[str, Any]:
    """Verify Odin can actually serve data with a live call, so the UI never shows a
    false green. Returns {ok, needs_reauth, signed_in_as, message}."""
    ident = auth_status().get("signed_in_as", "")
    try:
        _run(["clients", "--json"], timeout=30)
        return {"ok": True, "needs_reauth": False, "signed_in_as": ident,
                "message": f"Odin connected as {ident}"}
    except OdinAuthError as e:
        return {"ok": False, "needs_reauth": True, "signed_in_as": ident, "message": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "needs_reauth": False, "signed_in_as": ident,
                "message": f"Odin error: {e}"}


@lru_cache(maxsize=1)
def list_clients() -> list[dict[str, str]]:
    """Return [{id, name, domain}] of selectable Odin clients."""
    try:
        out = _run(["clients", "--json"], timeout=45)
    except OdinAuthError:
        list_clients.cache_clear()  # don't cache an auth failure — re-auth should recover
        raise
    data = json.loads(out)
    # tolerate either a bare list or {data:{clients:[...]}} shapes
    if isinstance(data, dict):
        data = data.get("data", data)
        data = data.get("clients", data) if isinstance(data, dict) else data
    clients = []
    for c in data:
        clients.append({
            "id": c.get("id") or c.get("client_id") or "",
            "name": c.get("name") or c.get("label") or c.get("id") or "",
            "domain": c.get("domain") or "",
        })
    return [c for c in clients if c["id"]]


def query(entity_type: str, scope: str, limit: int = 25,
          fields: list[str] | None = None, kind: str = "hospitality") -> list[dict]:
    args = ["query", entity_type, str(limit)]
    if fields:
        args.append("--fields=" + ",".join(fields))
    try:
        data = json.loads(_run(args, scope=scope, kind=kind))
    except OdinAuthError:
        raise
    except Exception:
        return []
    return data.get("data", {}).get("entities", []) if isinstance(data, dict) else []


def search(text: str, scope: str, limit: int = 15, kind: str = "hospitality") -> list[dict]:
    """Semantic search via the search_entities_semantic tool (uses top_k)."""
    payload = json.dumps({"query": text, "top_k": str(limit)})
    try:
        data = json.loads(_run(["call", "search_entities_semantic", payload],
                               scope=scope, kind=kind))
    except OdinAuthError:
        raise
    except Exception:
        return []
    d = data.get("data", data) if isinstance(data, dict) else {}
    return d.get("entities", d.get("results", [])) if isinstance(d, dict) else []


def _clean(entities: list[dict], keep: int) -> list[dict]:
    """Trim entity dicts to the human-meaningful, non-empty fields."""
    drop = {"embedding", "vector", "_embedding", "created_at", "updated_at"}
    out = []
    for e in entities[:keep]:
        row = {}
        for k, v in e.items():
            if k in drop or v in (None, "", [], {}):
                continue
            if isinstance(v, str) and len(v) > 600:
                v = v[:600] + "…"
            row[k] = v
        if row:
            out.append(row)
    return out


# --- deep grounding: relation traversal + provenance/freshness fact ledger ---

# human-meaningful metadata → short label (noisy midgard IDs are dropped)
_FACT_KEYS = {
    "address_line_1": "address", "primary_city": "city", "city": "city",
    "primary_state": "state", "state_name": "state",
    "primary_postal_code": "postal", "postal_code": "postal",
    "primary_country": "country", "country_name": "country",
    "primary_phone": "phone", "phone": "phone",
    "website_domain": "website", "profile_url": "website",
    "rating": "rating", "review_count": "reviews", "sentiment": "sentiment",
    "theme": "theme", "property_status": "status", "business_category_id": "category",
}
_FRESH_KEYS = ["midgard_profile_last_changed_date", "updated_at", "created_at"]


def find_related(entity_id: str, scope: str, kind: str = "hospitality") -> list[dict]:
    """Return [{rel_type, direction, entity}] for one node's outgoing+incoming edges."""
    try:
        data = json.loads(_run(["call", "find_related", json.dumps({"entity_id": entity_id})],
                               scope=scope, kind=kind))
    except OdinAuthError:
        raise
    except Exception:
        return []
    d = data.get("data", data) if isinstance(data, dict) else {}
    out = []
    for direction in ("outgoing", "incoming"):
        for rel in (d.get(direction) or []):
            ent = rel.get("entity")
            if ent:
                out.append({"rel_type": rel.get("rel_type", "related_to"),
                            "direction": direction, "entity": ent})
    return out


def _enrich(e: dict) -> dict:
    """Turn a raw node into a grounding record with facts, provenance, freshness."""
    md = e.get("metadata") or {}
    facts: dict[str, Any] = {}
    for k, label in _FACT_KEYS.items():
        v = md.get(k)
        if v not in (None, "", [], {}) and label not in facts:
            facts[label] = v
    fresh = next((md[k] for k in _FRESH_KEYS if md.get(k)), e.get("created_at"))
    prov = md.get("grounded_in") or []
    return {
        "id": e.get("id", ""),
        "type": e.get("entity_type") or e.get("type") or "entity",
        "name": e.get("name") or e.get("label") or e.get("id", ""),
        "description": (e.get("description") or "")[:1400],
        "facts": facts,
        "freshness": (str(fresh)[:10] if fresh else None),
        "provenance": prov if isinstance(prov, list) else [prov],
        "relations": [],
    }


def gather_grounding(scope: str, topic: str, entity_hints: list[str] | None = None,
                     kind: str = "hospitality", max_seeds: int = 18,
                     node_cap: int = 130, light: bool = False) -> dict[str, Any]:
    """Deep grounding bundle: core anchors + semantic seeds + 1-hop relation
    traversal, with full facts, provenance and freshness preserved.

    `light=True` skips the (slow) 1-hop relation traversal and uses fewer semantic
    seeds — fine for fast topic ideation, which needs entity breadth, not relations.

    Returns {node_type: [records]} plus a "_fact_ledger" of atomic, sourced facts.
    """
    nodes: dict[str, dict] = {}

    def add(raw: dict) -> str | None:
        nid = raw.get("id")
        if not nid:
            return None
        if nid not in nodes:
            nodes[nid] = _enrich(raw)
        return nid

    # 1) core anchors (full nodes, not trimmed field lists)
    core = {"brand": 6, "property": 18, "resort": 10, "hotel": 10, "review_theme": 18,
            "keyword": 22, "business_goal": 12, "business_problem": 8, "schema_type": 18,
            "google_business_profile": 10, "location": 12, "web_page": 12, "gap_analysis": 8}
    for etype, limit in core.items():
        for e in query(etype, scope, limit=limit, kind=kind):
            add(e)

    # 2) semantic seeds most relevant to the topic (fewer in light mode)
    seed_ids: list[str] = []
    n_seed_q, seed_lim = (4, 6) if light else (8, 10)
    for q in ([topic] + (entity_hints or []))[:n_seed_q]:
        for hit in search(q, scope, limit=seed_lim, kind=kind):
            nid = add(hit)
            if nid and nid not in seed_ids:
                seed_ids.append(nid)

    # 3) traverse relations from the strongest seeds (skipped in light mode — the slow part)
    if not light:
        anchors = seed_ids[:max_seeds]
        anchors += [nid for nid, n in nodes.items()
                    if n["type"] in ("brand", "property") and nid not in anchors][:6]
        for sid in anchors[:max_seeds + 6]:
            for rel in find_related(sid, scope, kind=kind):
                ent = rel["entity"]
                tgt_name = ent.get("name") or ent.get("id", "")
                # always record the relation; only add the target node if under the cap
                if ent.get("id") in nodes or len(nodes) < node_cap:
                    add(ent)
                if sid in nodes and tgt_name:
                    nodes[sid]["relations"].append(f"{rel['rel_type']} → {tgt_name}")

    # group by type + build the sourced fact ledger
    bundle: dict[str, Any] = {}
    ledger: list[dict] = []
    for n in list(nodes.values())[:node_cap]:
        bundle.setdefault(n["type"], []).append(n)
        for label, val in n["facts"].items():
            ledger.append({"fact": f"{n['name']} — {label}: {val}", "source": n["id"],
                           "provenance": n["provenance"], "freshness": n["freshness"]})
    bundle["_fact_ledger"] = ledger
    return bundle
