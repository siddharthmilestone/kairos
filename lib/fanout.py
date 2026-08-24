"""Query Fan-Out engine — maps the AI-search question space behind a topic.

Given the selected opportunity (and, for the optimize path, the crawled page), it
runs a staged decomposition via `claude -p` and returns a scored, classified set of
queries an AI search system would fan out to. When a page is present it also judges
evidence-based coverage, turning the fan-out into a gap analysis. The approved queries
become the answerability targets fed into content generation.

Grounded in the Odin CMG; never fabricates coverage or facts. Models publicly
documented query-fan-out behavior — not any proprietary retrieval system.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib import generate, taxonomy
from lib.prompt import render_grounding_context

TEMPLATE = Path(__file__).resolve().parent.parent / "prompts" / "query_fanout_prompt.md"
_FENCE = re.compile(r"<<<\s*FANOUT_JSON_START\s*>>>(.*?)<<<\s*FANOUT_JSON_END\s*>>>",
                    re.DOTALL | re.IGNORECASE)

# controlled taxonomy (build-notes §8) — used for grouping / filtering in the UI
DECISION_STAGES = ["Awareness", "Education", "Discovery", "Consideration",
                   "Evaluation", "Validation", "Decision", "Post-purchase"]
COVERAGE_CLASSES = ["Fully Covered", "Contextually Covered", "Partially Covered",
                    "Unsupported", "Contradicted", "Not Applicable"]
# importance band → label (build-notes §14)
_BANDS = [(90, "Critical"), (75, "High"), (50, "Medium"), (25, "Low"), (0, "Noise")]

DEPTHS = {"Standard (depth 2)": 2, "Deep (depth 3)": 3}

# --- Information-Gain reframe: decision-criteria classes + deterministic scoring ---
# The 3-bucket white-space model (§2): where information gain actually lives.
WHITESPACE_CLASSES = ["White space", "Parity gap", "Answered"]
# Bill Hunt's Click-Worthiness gate (§D): single-fact → fast FAQ & stop; multi-criteria → deep.
CLICK_WORTHINESS = ["Decision-criteria", "Single-fact"]
ANSWERABLE_FROM = ["Odin", "First-party needed", "Public"]

# priority = Opportunity × Competition × Click-Worthiness (§D8). The last two are
# multipliers, computed in code so scoring is transparent and consistent — not the LLM's.
_COMPETITION_MULT = {"White space": 1.0, "Parity gap": 0.65, "Answered": 0.25}
_CLICKWORTH_MULT = {"Decision-criteria": 1.0, "Single-fact": 0.35}

# --- Qforia fan-out classification (Mike King / iPullRank, modelling Google's query
# fan-out patterns) — the 6 canonical query types the UI table surfaces. This sits ALONGSIDE
# the internal 14-value `type` + criteria taxonomy (which drives scoring); it is the
# user-facing "how the engine expanded this query" classification. Exactly one per query.
QFORIA_TYPES = ["Reformulation", "Related Query", "Comparative Query",
                "Implicit Query", "Entity Expansion", "Personalized Query"]
# how each type maps from loose model output → the canonical label
_QFORIA_ALIASES = {
    "reformulation": "Reformulation", "rephrase": "Reformulation", "reworded": "Reformulation",
    "synonym": "Reformulation", "equivalent": "Reformulation",
    "related": "Related Query", "related query": "Related Query", "adjacent": "Related Query",
    "follow-up": "Related Query", "follow up": "Related Query",
    "comparative": "Comparative Query", "comparison": "Comparative Query", "compare": "Comparative Query",
    "versus": "Comparative Query", "vs": "Comparative Query",
    "implicit": "Implicit Query", "unstated": "Implicit Query", "inferred": "Implicit Query",
    "implied": "Implicit Query",
    "entity expansion": "Entity Expansion", "entity": "Entity Expansion", "expansion": "Entity Expansion",
    "named entity": "Entity Expansion",
    "personalized": "Personalized Query", "personalised": "Personalized Query",
    "persona": "Personalized Query", "contextual": "Personalized Query",
}


def normalize_qforia_type(v: Any) -> str:
    """Coerce a model-supplied type onto exactly one of the 6 Qforia types."""
    t = str(v or "").strip().lower()
    if not t:
        return "Related Query"
    for label in QFORIA_TYPES:  # exact (case-insensitive) match first
        if t == label.lower():
            return label
    for key, label in _QFORIA_ALIASES.items():  # then alias/substring
        if key in t:
            return label
    return "Related Query"


def importance_band(score: Any) -> str:
    try:
        s = int(score)
    except Exception:
        return "—"
    return next(label for cut, label in _BANDS if s >= cut)


def _normalize_whitespace(v: Any) -> str:
    t = str(v or "").lower()
    if any(k in t for k in ("white", "no one", "nobody", "unanswered", "not answered by any")):
        return "White space"
    if any(k in t for k in ("parity", "competitor")):
        return "Parity gap"
    if any(k in t for k in ("we already", "already answer", "we answer", "answered by you",
                            "ours", "done", "answered", "covered")):
        return "Answered"
    return "Parity gap"  # safe default: treat unknown as the old kind of gap


def _normalize_clickworth(v: Any) -> str:
    t = str(v or "").lower()
    if "single" in t or "one-fact" in t or "one fact" in t or "fact-lookup" in t or "lookup" in t:
        return "Single-fact"
    return "Decision-criteria"


def compute_priority(opportunity: int, whitespace: str, click_worthiness: str) -> int:
    """priority = Opportunity × Competition × Click-Worthiness, on a 0–100 scale."""
    o = max(0, min(100, int(opportunity or 0))) / 100.0
    c = _COMPETITION_MULT.get(whitespace, 0.65)
    w = _CLICKWORTH_MULT.get(click_worthiness, 1.0)
    return round(100 * o * c * w)


def _compact(bundle: dict[str, Any], max_per_type: int = 7, max_ledger: int = 20) -> dict[str, Any]:
    """Slim the grounding for the fan-out prompt: node names + a few facts, dropping the long
    descriptions/relations/provenance that bloat the render. Keeps the prompt small so the
    (tool-free) generation is fast. No-op for a public/LLM bundle."""
    if not bundle or bundle.get("_source") == "llm":
        return bundle
    out: dict[str, Any] = {}
    for k, v in bundle.items():
        if k == "_fact_ledger" and isinstance(v, list):
            out[k] = v[:max_ledger]
        elif k.startswith("_"):
            out[k] = v
        elif isinstance(v, list):
            rows = []
            for r in v[:max_per_type]:
                if isinstance(r, dict):
                    node = {"id": r.get("id", ""), "name": r.get("name", ""), "type": r.get("type", "")}
                    if r.get("facts"):
                        node["facts"] = dict(list(r["facts"].items())[:3])
                    rows.append(node)
                else:
                    rows.append(r)
            out[k] = rows
        else:
            out[k] = v
    return out


def _mode_block(has_page: bool) -> str:
    if has_page:
        return ("**MODE: HYBRID (content + coverage).** An existing page is supplied under EXISTING "
                "PAGE. Generate the fan-out AND judge, for each query, whether the page (backed by the "
                "grounding context) answers it with evidence.")
    return ("**MODE: CONTENT PLANNING (fan-out only).** No page exists yet. Map the full query fan-out "
            "and information needs this new content must satisfy. Leave coverage fields null.")


def _existing_page_block(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return ""
    h = snapshot.get("headings", {})
    return "\n".join([
        "# EXISTING PAGE (judge coverage against this + the grounding context)",
        f"- URL: {snapshot.get('url','')}",
        f"- Title: {snapshot.get('title','')}",
        f"- Meta: {snapshot.get('meta_description','')}",
        f"- Schema present: {', '.join(snapshot.get('schema_types', [])) or 'none'}",
        f"- H1/H2: {' | '.join((h.get('h1', []) + h.get('h2', []))[:16])}",
        "",
        "Existing body copy:",
        "```",
        (snapshot.get("body_text", "") or "")[:45000],
        "```",
        "",
    ])


def _coverage_instructions(has_page: bool) -> str:
    if has_page:
        return ("For every query, assign `coverage` (one of Fully Covered / Contextually Covered / "
                "Partially Covered / Unsupported / Contradicted / Not Applicable), a `coverage_pct` 0–100, "
                "a one-line `evidence_note` (what on the page supports it, or what is missing), and a "
                "`recommendation`. Coverage must be evidence-based — a keyword appearing is NOT coverage. "
                "Then set `summary.answerability_coverage` = importance-weighted % of queries that are "
                "Fully/Contextually covered, and count `critical_gaps` (importance ≥ 75 and Unsupported/"
                "Partially/Contradicted).")
    return ("Leave `coverage`, `coverage_pct`, and `evidence_note` null. Still provide a `recommendation` "
            "for what the new content must include to satisfy each query, and leave "
            "`summary.answerability_coverage` null.")


def detect_type(opp: dict[str, Any], brand_name: str, grounding_bundle: dict[str, Any]) -> str:
    """Heuristic hospitality-type hint from the topic, brand, keywords, entities and the
    grounded entity names (the fan-out LLM confirms or overrides it)."""
    blob_parts = [opp.get("core_topic", ""), brand_name, opp.get("pillar_topic", ""),
                  " ".join(opp.get("keywords") or []), " ".join(opp.get("entities") or [])]
    for etype, rows in (grounding_bundle or {}).items():
        if etype.startswith("_") or not isinstance(rows, list):
            continue
        for r in rows[:20]:
            if isinstance(r, dict):
                blob_parts.append(str(r.get("name", "")))
    return taxonomy.detect_hospitality_type(" ".join(blob_parts))


def build_prompt(*, opp: dict[str, Any], brand_name: str, target_audience: str,
                 output_language: str, grounding_bundle: dict[str, Any],
                 page_snapshot: dict[str, Any] | None, depth: int, fanout_limit: int,
                 hospitality_type: str = "") -> str:
    has_page = bool(page_snapshot)
    keywords = opp.get("keywords") or []
    htype = hospitality_type or detect_type(opp, brand_name, grounding_bundle)
    seed_prompts = opp.get("prompts") or []
    seed_prompts_str = ("; ".join(str(p) for p in seed_prompts) if seed_prompts
                        else "(none supplied — derive the 5 originals from the topic and keywords)")
    filled = {
        "{mode_block}": _mode_block(has_page),
        "{brand_name}": brand_name or "",
        "{seed_topic}": opp.get("core_topic", ""),
        "{seed_prompts}": seed_prompts_str,
        "{primary_keyword}": keywords[0] if keywords else opp.get("core_topic", ""),
        "{search_intent}": opp.get("intent", "Informational"),
        "{entities}": ", ".join(opp.get("entities", [])) or "(from grounding)",
        "{target_audience}": target_audience or "(general audience)",
        "{output_language}": output_language or "English",
        "{grounding_context}": render_grounding_context(_compact(grounding_bundle)),
        "{existing_page_block}": _existing_page_block(page_snapshot),
        "{depth}": str(depth),
        "{fanout_limit}": str(fanout_limit),
        "{coverage_instructions}": _coverage_instructions(has_page),
        "{hospitality_type}": htype or "(classify it yourself from the grounding)",
        "{criteria_taxonomy}": taxonomy.criteria_taxonomy_block(htype),
    }
    template = TEMPLATE.read_text()
    for k, v in filled.items():
        template = template.replace(k, str(v))
    return template


def _parse(out: str) -> dict:
    candidates: list[str] = []
    m = _FENCE.search(out)
    if m:
        candidates.append(m.group(1))
    candidates += re.findall(r"```(?:json)?\s*(.*?)```", out, flags=re.DOTALL)
    if "{" in out and "}" in out:
        candidates.append(out[out.index("{"): out.rindex("}") + 1])
    candidates.append(out)
    for c in candidates:
        c = c.strip()
        if not c:
            continue
        try:
            data = json.loads(c)
            if isinstance(data, dict) and "queries" in data:
                return data
        except Exception:
            continue
    raise ValueError(f"Could not parse the fan-out JSON. Response began: {out[:200]!r}")


def _postprocess(q: dict, i: int) -> dict:
    """Normalize the criteria fields and compute the Opportunity×Competition×Click-Worthiness
    priority in code (transparent + consistent). Back-compatible: `importance` becomes the
    computed priority so all existing sorting/UI keeps working, while `opportunity` preserves
    the model's raw 0–100 value-of-the-question estimate."""
    q.setdefault("id", f"q{i+1:03d}")
    try:
        raw = int(q.get("opportunity", q.get("importance", 0)))
    except Exception:
        raw = 0
    ws = _normalize_whitespace(q.get("whitespace"))
    cw = _normalize_clickworth(q.get("click_worthiness"))
    q["opportunity"] = raw
    q["whitespace"] = ws
    q["click_worthiness"] = cw
    q["faq_only"] = (cw == "Single-fact")
    q["priority"] = compute_priority(raw, ws, cw)
    q["importance"] = q["priority"]  # back-compat: existing sort/pre-select/UI use importance
    # Qforia table fields (one each per query). reasoning falls back to why_generated so the
    # column is never empty; user_intent falls back to the controlled intent as a last resort.
    q["qforia_type"] = normalize_qforia_type(q.get("qforia_type") or q.get("type"))
    q.setdefault("original_id", "")
    q.setdefault("original_query", "")
    if not q.get("user_intent"):
        q["user_intent"] = q.get("intent", "") or ""
    if not q.get("reasoning"):
        q["reasoning"] = q.get("why_generated", "") or ""
    # sane defaults for the remaining criteria fields
    q.setdefault("criteria_category", "")
    q.setdefault("criteria_scope", "")
    q.setdefault("answerable_from", "Public")
    if not isinstance(q.get("scorecard"), list):
        q["scorecard"] = []
    return q


def run_fanout(*, opp: dict[str, Any], brand_name: str, target_audience: str,
               output_language: str, grounding_bundle: dict[str, Any],
               page_snapshot: dict[str, Any] | None = None, depth: int = 2,
               fanout_limit: int = 20, model: str = "haiku",
               hospitality_type: str = "") -> dict:
    """Generate + parse the criteria-aware query fan-out. Returns the validated dict.

    allow_tools=False: the fan-out is graph-grounded reasoning + Qforia classification and must
    NOT browse the web. Web browsing (for competitor/SERP signals) was making this step take
    several minutes; competitor coverage is now judged from the grounding + the model's own
    knowledge, which is fast and needs no SERP dependency."""
    prompt_text = build_prompt(
        opp=opp, brand_name=brand_name, target_audience=target_audience,
        output_language=output_language, grounding_bundle=grounding_bundle,
        page_snapshot=page_snapshot, depth=depth, fanout_limit=fanout_limit,
        hospitality_type=hospitality_type)
    out = generate.generate(prompt_text, model=model, timeout=300, allow_tools=False)
    data = _parse(out)
    qs = data.get("queries") or []
    if not qs:
        raise ValueError("The fan-out returned no queries. Try again.")
    qs = [_postprocess(q, i) for i, q in enumerate(qs)]
    # Normalize the 5 derived original queries and back-fill each sub-query's original_query
    # text from its original_id (so the UI table can group under the original without a lookup).
    originals = _normalize_originals(data.get("original_queries"), qs)
    data["original_queries"] = originals
    omap = {o["id"]: o["query"] for o in originals}
    for q in qs:
        if not q.get("original_query"):
            q["original_query"] = omap.get(q.get("original_id"), "")
    # lead with the highest-priority queries (white-space, decision-criteria float up)
    data["queries"] = sorted(qs, key=lambda q: q.get("priority", 0), reverse=True)
    # roll the 3-bucket + gate counts into the summary the UI reads
    summ = data.get("summary") or {}
    ws_counts = whitespace_summary(qs)
    summ["white_space"] = ws_counts.get("White space", 0)
    summ["parity_gap"] = ws_counts.get("Parity gap", 0)
    summ["answered"] = ws_counts.get("Answered", 0)
    summ["faq_only"] = sum(1 for q in qs if q.get("faq_only"))
    summ["first_party_needed"] = sum(1 for q in qs if q.get("answerable_from") == "First-party needed")
    summ.setdefault("hospitality_type",
                    data.get("hospitality_type")
                    or detect_type(opp, brand_name, grounding_bundle) or "")
    data["summary"] = summ
    return data


def _normalize_originals(originals: Any, queries: list[dict]) -> list[dict]:
    """Return the 5 original (seed) queries as [{id, query, intent}]. If the model omitted them,
    reconstruct from the distinct original_query/original_id values on the sub-queries so the UI
    always has parents to group under."""
    out: list[dict] = []
    seen = set()
    if isinstance(originals, list):
        for i, o in enumerate(originals):
            if isinstance(o, dict):
                oid = o.get("id") or f"o{i+1}"
                text = (o.get("query") or o.get("text") or "").strip()
            else:
                oid, text = f"o{i+1}", str(o).strip()
            if text and oid not in seen:
                seen.add(oid)
                out.append({"id": oid, "query": text, "intent": (o.get("intent", "") if isinstance(o, dict) else "")})
    if out:
        return out
    # fallback: rebuild from sub-queries
    for q in queries:
        oid = q.get("original_id") or ""
        text = (q.get("original_query") or "").strip()
        key = oid or text
        if text and key not in seen:
            seen.add(key)
            out.append({"id": oid or f"o{len(out)+1}", "query": text, "intent": ""})
    return out


def group_by_original(fo: dict) -> list[dict]:
    """Group the fan-out queries under their 5 original queries for the UI table.
    Returns [{original: {...}, queries: [...]}] in original order, with any orphans
    (no matching original) collected under a trailing 'Other' bucket."""
    originals = fo.get("original_queries") or _normalize_originals(None, fo.get("queries") or [])
    queries = fo.get("queries") or []
    by_id: dict[str, list[dict]] = {}
    by_text: dict[str, list[dict]] = {}
    for q in queries:
        if q.get("original_id"):
            by_id.setdefault(q["original_id"], []).append(q)
        elif q.get("original_query"):
            by_text.setdefault(q["original_query"].strip().lower(), []).append(q)
    groups: list[dict] = []
    claimed = set()
    for o in originals:
        qs = list(by_id.get(o["id"], [])) + list(by_text.get((o["query"] or "").strip().lower(), []))
        for q in qs:
            claimed.add(id(q))
        qs = sorted(qs, key=lambda q: q.get("priority", q.get("importance", 0)), reverse=True)
        groups.append({"original": o, "queries": qs})
    orphans = [q for q in queries if id(q) not in claimed]
    if orphans:
        groups.append({"original": {"id": "other", "query": "Other / unmapped", "intent": ""},
                       "queries": sorted(orphans, key=lambda q: q.get("priority", 0), reverse=True)})
    return groups


def coverage_summary(queries: list[dict]) -> dict[str, int]:
    """Count queries by coverage class (for the optimize scorecard)."""
    out: dict[str, int] = {}
    for q in queries:
        c = q.get("coverage")
        if c:
            out[c] = out.get(c, 0) + 1
    return out


def whitespace_summary(queries: list[dict]) -> dict[str, int]:
    """Count queries by 3-bucket white-space class."""
    out: dict[str, int] = {}
    for q in queries:
        c = q.get("whitespace")
        if c:
            out[c] = out.get(c, 0) + 1
    return out


def default_selected_ids(queries: list[dict], min_priority: int = 45) -> list[str]:
    """Pre-select the information-gain targets: true white space + high-priority
    decision-criteria (and, on the optimize path, weakly-covered queries). Single-fact
    'FAQ-only' queries are NOT pre-selected as deep targets — they feed the FAQ instead."""
    ids = []
    for q in queries:
        if q.get("faq_only"):
            continue
        weak = (q.get("coverage") or "") in ("Unsupported", "Partially Covered", "Contradicted")
        if (q.get("whitespace") == "White space"
                or q.get("priority", q.get("importance", 0)) >= min_priority or weak):
            ids.append(q["id"])
    return ids or [q["id"] for q in queries if not q.get("faq_only")][:8] or [q["id"] for q in queries[:8]]
