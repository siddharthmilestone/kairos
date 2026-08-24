"""Consult customer-provided source material (off-graph artifacts) in Odin.

Implements the artifact-consultation contract: the graph is the index — discover
the store dynamically, prefer distilled graph entities, drop to raw artifacts only
for verbatim/recency/coverage, cite every artifact's `url_key` for provenance, and
stay strictly READ-ONLY.

Discovery path (per the contract):
  1. query_entities {entity_type: document_collection}   → signpost anchors (kind_tag / dataset_slug / url_key)
  2. manage_artifact {action: list}                       → source_file artifacts, filter by an anchor's kind_tag
  3. get_artifact_document {url_key}                      → extracted document text
  4. query_dataset {artifact_url_key, sql}               → row-level evidence (reviews / conversations)

For the PR agent the FOCUS is: news-press (prior releases & PR/agency reports),
performance-data reports, newsletters, business-details/goals, and customer problems
(distilled entities first). Everything here is best-effort and guarded: if the store
is empty or unreachable the caller simply gets an empty brief and falls back to the
graph grounding — never an error that blocks generation.
"""
from __future__ import annotations

import json
from typing import Any

from lib import odin

# governed FOCUS for the PR / news-release agent (see artifact-consultation contract)
FOCUS_KINDS = {"news-press", "performance-data", "business-details"}
# releases drive the "never re-announce" ledger + voice samples; context aligns angles to goals/perf.
RELEASE_KINDS = {"news-press"}
CONTEXT_KINDS = {"performance-data", "business-details"}
FOCUS_KEYWORDS = ("news", "press", "release", "newsletter", "report", "performance",
                  "problem", "pain", "complaint", "agency", "media", "coverage")
_DATE_KEYS = ("observed_at", "published_at", "created_at", "date", "released_at")
_MONTHS_L = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}


def _tag_slugs(rec: dict) -> list[str]:
    """Governed tag slugs. Odin tags are dicts like {'slug':'news-press', ...}; be
    tolerant of plain strings too."""
    out = []
    for t in (rec.get("tags") or _meta(rec).get("tags") or []):
        if isinstance(t, dict) and t.get("slug"):
            out.append(str(t["slug"]).lower())
        elif isinstance(t, str):
            out.append(t.lower())
    return out


def _title_date(title: str) -> str:
    """Rough sortable date (YYYY-MM) parsed from a release title (Odin ingest dates are
    all the upload day, so the real date lives in the filename/title, e.g. '…June 2026')."""
    import re
    t = title or ""
    y = re.search(r"20\d{2}", t)
    if not y:
        return ""
    mon = next((f"{i:02d}" for name, i in _MONTHS_L.items() if name in t.lower()), "00")
    return f"{y.group()}-{mon}"


def _call(name: str, payload: dict, scope: str, kind: str = "hospitality",
          timeout: int = 25) -> Any:
    """Run one `odin call <name> <json>` read-only. Returns the unwrapped `data`
    payload, or None on any failure (so a missing verb / empty store degrades
    gracefully). OdinAuthError is re-raised so the UI can prompt re-auth."""
    try:
        out = odin._run(["call", name, json.dumps(payload)], scope=scope, kind=kind, timeout=timeout)
        data = json.loads(out)
    except odin.OdinAuthError:
        raise
    except Exception:
        return None
    if isinstance(data, dict):
        return data.get("data", data)
    return data


def _as_list(data: Any, *keys: str) -> list[dict]:
    """Pull a list of records out of assorted response shapes."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for k in (*keys, "entities", "results", "artifacts", "items", "rows"):
            v = data.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def _meta(rec: dict) -> dict:
    m = rec.get("metadata")
    return m if isinstance(m, dict) else {}


def _artifact_date(a: dict) -> str:
    m = _meta(a)
    for k in _DATE_KEYS:
        v = a.get(k) or m.get(k)
        if v:
            return str(v)
    return ""


def list_document_collections(scope: str, kind: str = "hospitality") -> list[dict]:
    """Signpost anchors: each says what a library holds and how to reach it."""
    data = _call("query_entities", {"entity_type": "document_collection", "limit": 20}, scope, kind)
    out = []
    for c in _as_list(data):
        m = _meta(c)
        out.append({
            "id": c.get("id") or c.get("entity_id") or "",
            "name": c.get("name") or c.get("label") or c.get("title") or c.get("id") or "",
            "description": (c.get("description") or "").strip(),
            "kind_tag": m.get("kind_tag") or c.get("kind_tag"),
            "dataset_slug": m.get("dataset_slug") or c.get("dataset_slug"),
            "url_key": m.get("url_key") or c.get("url_key"),
        })
    return out


def list_artifacts(scope: str, kind: str = "hospitality") -> list[dict]:
    """All artifacts (we filter by governed tag / content_class / keyword downstream)."""
    data = _call("manage_artifact", {"action": "list"}, scope, kind, timeout=40)
    out = []
    for a in _as_list(data):
        title = a.get("title") or a.get("name") or a.get("filename") or a.get("id") or ""
        out.append({
            "url_key": a.get("url_key") or _meta(a).get("url_key") or a.get("id"),
            "title": title,
            "tags": _tag_slugs(a),
            "content_class": (a.get("content_class") or a.get("artifact_type") or "").lower(),
            "date": _title_date(title) or _artifact_date(a)[:10],
        })
    return [a for a in out if a["url_key"]]


def get_document(scope: str, url_key: str, kind: str = "hospitality") -> str:
    """Extracted text (Odin returns it under data.markdown). Spreadsheets return empty
    text by design — query their derived dataset artifact instead."""
    data = _call("get_artifact_document", {"url_key": url_key}, scope, kind, timeout=40)
    if isinstance(data, dict):
        return (data.get("markdown") or data.get("text") or data.get("content")
                or data.get("document") or "").strip()
    return (data or "").strip() if isinstance(data, str) else ""


def query_dataset(scope: str, artifact_url_key: str, sql: str, kind: str = "hospitality") -> list[dict]:
    """Row-level evidence from a derived dataset artifact (verbatim, source language)."""
    data = _call("query_dataset", {"artifact_url_key": artifact_url_key, "sql": sql}, scope, kind, timeout=30)
    return _as_list(data)


def _is_doc(a: dict) -> bool:
    return a["content_class"] in ("source_file", "freeform", "")  # not 'collection'/'dataset'


def _is_release(a: dict) -> bool:
    if not _is_doc(a):
        return False
    if any(t in RELEASE_KINDS for t in a["tags"]):
        return True
    return "newsletter" in (a["title"] + " " + " ".join(a["tags"])).lower()


def _is_context(a: dict) -> bool:
    return _is_doc(a) and any(t in CONTEXT_KINDS for t in a["tags"]) and not _is_release(a)


def gather_pr_artifacts(scope: str, *, max_docs: int = 1, per_doc_chars: int = 600,
                        ledger_cap: int = 12, kind: str = "hospitality") -> dict:
    """Follow the discovery path and return a provenance-carrying brief:
      • `ledger`  — every prior PR artifact's title + url_key (the 'already-announced'
                    list, so the plan never re-announces one);
      • `documents` — full extracted text of the most recent few (for voice/structure).

    Read-only and fully guarded — any failure yields an empty-but-valid brief so the
    caller falls back to graph grounding. Distilled entities (business_goal /
    business_problem / review_theme) are already in the grounding bundle; this adds the
    RAW material the graph points to.
    """
    brief: dict[str, Any] = {"available": False, "documents": [], "ledger": [],
                             "context": [], "collections": [], "error": None}
    try:
        cols = list_document_collections(scope, kind)
    except odin.OdinAuthError:
        raise
    except Exception as e:  # noqa: BLE001
        brief["error"] = str(e)
        return brief

    for c in cols:
        brief["collections"].append({"name": c["name"], "kind_tag": c.get("kind_tag"),
                                     "description": c["description"][:200], "url_key": c.get("url_key")})

    try:
        arts = list_artifacts(scope, kind)
    except odin.OdinAuthError:
        raise
    except Exception:  # noqa: BLE001
        arts = []

    releases = sorted([a for a in arts if _is_release(a)], key=lambda a: a.get("date", ""), reverse=True)
    context = sorted([a for a in arts if _is_context(a)], key=lambda a: a.get("date", ""), reverse=True)

    # 1) "already-announced" ledger — the actual prior RELEASES (never re-announce these)
    for a in releases[:ledger_cap]:
        brief["ledger"].append({"url_key": a["url_key"], "title": a["title"], "date": a.get("date", ""),
                                "kind": next((t for t in a["tags"] if t in RELEASE_KINDS), "news-press")})

    # 2) read the most recent releases in full — for voice & structure
    for a in releases[:max_docs]:
        try:
            text = get_document(scope, a["url_key"], kind)
        except odin.OdinAuthError:
            raise
        except Exception:  # noqa: BLE001
            text = ""
        if text:
            brief["documents"].append({
                "url_key": a["url_key"], "title": a["title"] or a["url_key"],
                "date": a.get("date", ""), "tags": a.get("tags") or [],
                "excerpt": text[:per_doc_chars],
            })

    # 3) business/performance context — titles only (align angles to goals & performance)
    for a in context[:6]:
        brief["context"].append({"url_key": a["url_key"], "title": a["title"], "date": a.get("date", ""),
                                 "kind": next((t for t in a["tags"] if t in CONTEXT_KINDS), "")})

    brief["available"] = bool(brief["ledger"] or brief["documents"] or brief["collections"])
    return brief


def render_pr_artifact_brief(brief: dict | None) -> str:
    """Render the artifact brief into a prompt block: graph-first, never-re-announce,
    align-to-goals, cite url_key. Safe when the brief is empty."""
    brief = brief or {}
    ledger = brief.get("ledger") or []
    docs = brief.get("documents") or []
    if not ledger and not docs:
        cols = brief.get("collections") or []
        if cols:
            names = ", ".join(c.get("name", "") for c in cols[:8] if c.get("name"))
            return ("# OFF-GRAPH SOURCE MATERIAL (customer-provided artifacts — READ-ONLY)\n"
                    f"The graph lists these artifact collections ({names}) but no individual PR "
                    "documents were readable this run. Rely on the graph grounding; do NOT invent "
                    "prior coverage, dates, or releases.")
        return ("# OFF-GRAPH SOURCE MATERIAL (customer-provided artifacts — READ-ONLY)\n"
                "No customer-provided PR artifacts were found in the store for this business. Rely on "
                "the graph grounding; do NOT invent prior coverage, dates, or releases.")
    lines = [
        "# OFF-GRAPH SOURCE MATERIAL — customer-provided PR artifacts (READ-ONLY; cite url_key)",
        "These are RAW prior artifacts the graph points to (press releases, newsletters, PR / "
        "performance reports). Consult them graph-first and use them to:",
        "- **NEVER re-announce** a story already covered in the ledger below — check every prior title "
        "before scheduling; each month's stories must be genuinely new.",
        "- Match the brand's established **voice, structure and recurring angles** (see the full-text samples).",
        "- Align each month to the stated **business goals**.",
        "For every story, record which artifacts you build on or deliberately avoid re-announcing, "
        "by `url_key`, in the `prior_coverage` field. Never fabricate an artifact or a url_key.",
        "",
        f"## Already announced — do NOT re-announce ({len(ledger)} prior artifacts):",
    ]
    for a in ledger:
        kind = f"[{a['kind']}] " if a.get("kind") else ""
        dt = f" ({a['date']})" if a.get("date") else ""
        lines.append(f"- {kind}\"{a['title']}\"{dt} — url_key: {a['url_key']}")
    if docs:
        lines.append("")
        lines.append("## Recent releases read in full (for voice & structure):")
        for d in docs:
            dt = f" ({d['date']})" if d.get("date") else ""
            lines.append(f"- \"{d['title']}\"{dt} — url_key: {d['url_key']}")
            if d.get("excerpt"):
                lines.append(f"    excerpt: {d['excerpt']}")
    context = brief.get("context") or []
    if context:
        lines.append("")
        lines.append("## Business & performance context (align each month's angle to these):")
        for a in context:
            kind = f"[{a['kind']}] " if a.get("kind") else ""
            lines.append(f"- {kind}\"{a['title']}\" — url_key: {a['url_key']}")
    return "\n".join(lines)
