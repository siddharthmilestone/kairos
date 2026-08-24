"""PR Calendar Operating System — grounded, KAIROS-reasoned 12-month calendar.

When the output format is "Press Release Calendar", this generates one high-value,
contextual press-release story per month, grounded in the Odin memory graph
(historical PR performance, competitor analysis, guest interests, existing PR
calendars, business objectives). Each month is scored on the PR model
(Newsworthiness × Brand Relevance × Audience Relevance × Media Potential × Timing).

Selecting a month maps it onto the standard opportunity record so it flows straight
into the existing fan-out → generate → validate pipeline as a Press Release.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib import generate, taxonomy
from lib.prompt import render_grounding_context

TEMPLATE = Path(__file__).resolve().parent.parent / "prompts" / "pr_calendar_prompt.md"
_FENCE = re.compile(r"<<<\s*PRCAL_JSON_START\s*>>>(.*?)<<<\s*PRCAL_JSON_END\s*>>>",
                    re.DOTALL | re.IGNORECASE)
_MONTHS = ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]


MAX_PER_MONTH = 2  # two complementary press releases per month (primary + secondary), 24/year

# The five PR-scoring dimensions (each 1–5) + a plain description for the UI explainer.
SCORE_DIMENSIONS = [
    ("newsworthiness", "Newsworthiness", "Is this genuinely new / news-driven — not promotion?"),
    ("brand_relevance", "Brand Relevance", "Can the brand credibly own it, with grounded authority?"),
    ("audience_relevance", "Audience Relevance", "Does the target audience actually care?"),
    ("media_potential", "Media Potential", "Will journalists and outlets pick it up?"),
    ("timing", "Timing", "Is the month / seasonality right for it?"),
]
PRIORITY_BANDS = [("High", 1000), ("Medium", 300), ("Low", 0)]


def priority_of(pr_score: Any) -> str:
    try:
        s = int(pr_score)
    except Exception:
        return "Medium"
    return "High" if s >= 1000 else "Medium" if s >= 300 else "Low"


def scoring_explainer() -> dict[str, Any]:
    """Structured explanation of how the PR score is calculated (for the UI + docs)."""
    return {
        "dimensions": SCORE_DIMENSIONS,
        "formula": "pr_score = Newsworthiness × Brand Relevance × Audience Relevance "
                   "× Media Potential × Timing",
        "range": "1 (all dimensions = 1) to 3125 (all dimensions = 5)",
        "why_multiplicative": "The score is a PRODUCT, not a sum — so a single weak axis "
                              "(e.g. Media Potential = 1) drags the whole score down. This is "
                              "deliberate: a story that fails on any one axis is not worth pitching, "
                              "however strong it is elsewhere.",
        "bands": [("High", "≥ 1000", "pitch-ready flagship story"),
                  ("Medium", "300–999", "solid, worth developing"),
                  ("Low", "< 300", "weak on at least one axis — background/fill only")],
        "worked": [("5·5·5·5·5", 3125, "High"), ("4·4·4·4·4", 1024, "High"),
                   ("5·5·4·3·5", 1500, "High"), ("3·3·3·3·3", 243, "Low")],
    }


def _trim_bundle(bundle: dict[str, Any], max_per_type: int = 6, max_ledger: int = 18) -> dict[str, Any]:
    """Lighten the grounding for PR PLANNING. Generation is dominated by the fixed cost of
    ingesting the prompt (a full grounding render is ~30KB and makes each call deliberate for
    minutes), so planning gets a COMPACT bundle: each node keeps only id/name/type + a few
    short facts — the long descriptions, relations and provenance (the bulk of the render) are
    dropped, and counts are capped. This shrinks the prompt ~4x, which is what lets the calendar
    generate in a reasonable time. PR needs entity breadth (brands, properties, awards, goals,
    review themes) + a short fact ledger, not the full subgraph."""
    if not bundle or bundle.get("_source") == "llm":
        return bundle
    out: dict[str, Any] = {}
    for k, v in bundle.items():
        if k == "_fact_ledger" and isinstance(v, list):
            out[k] = v[:max_ledger]
        elif k.startswith("_"):
            out[k] = v
        elif isinstance(v, list):
            compact = []
            for r in v[:max_per_type]:
                if not isinstance(r, dict):
                    compact.append(r)
                    continue
                node = {"id": r.get("id", ""), "name": r.get("name", ""), "type": r.get("type", "")}
                facts = r.get("facts") or {}
                if facts:
                    node["facts"] = dict(list(facts.items())[:4])
                compact.append(node)
            out[k] = compact
        else:
            out[k] = v
    return out


# In lean mode the calendar pass emits only the fields the picker + scoring need; the heavy
# per-story brief (proof points, media targets, spokesperson, prior-coverage provenance,
# keywords, prompts, grounding nodes, brand POV) is generated on demand by enrich_story() for
# the ONE story the user opens/selects. This roughly halves per-story reasoning, which is what
# gets 24 grounded stories from ~150s down toward ~70-80s.
_LEAN_OVERRIDE = """

--------------------------------------------------

# FAST CALENDAR MODE — OVERRIDES THE OUTPUT SCHEMA ABOVE
Emit ONLY these fields per story, and OMIT every other field (the full brief is generated later,
on demand, for the story the editor opens):
  month, month_index, story_rank, title, story_type, opportunity_type, narrative,
  business_objective, audience, news_hook, why_this_month,
  scores {newsworthiness, brand_relevance, audience_relevance, media_potential, timing},
  pr_score, priority
Still obey the never-re-announce rule (check each story against the source material), and still
derive scores properly — but do NOT emit proof_points, brand_pov, spokesperson, media_targets,
keywords, entities, grounding_nodes, prior_coverage, prompts or intent in this pass. Keep every
field to one tight line. Speed matters: dense, grounded, terse story seeds, no filler.
"""


def _build_prompt(brand_name: str, grounding_bundle: dict[str, Any], year: int,
                  artifact_brief: str = "",
                  month_scope: str = "all 12 months, January through December",
                  lean: bool = True) -> str:
    objectives = "; ".join(taxonomy.DEFAULT_OBJECTIVES)
    filled = {
        "{brand_name}": brand_name or "",
        "{year}": str(year),
        "{objectives}": objectives,
        "{month_scope}": month_scope,
        "{grounding_context}": render_grounding_context(_trim_bundle(grounding_bundle)),
        "{artifact_brief}": artifact_brief or
        "(No off-graph PR artifacts supplied — rely on the graph grounding; do not invent prior coverage.)",
    }
    template = TEMPLATE.read_text()
    for k, v in filled.items():
        template = template.replace(k, str(v))
    if lean:
        template += _LEAN_OVERRIDE
    return template


def _build_fast_prompt(brand_name: str, grounding_bundle: dict[str, Any], year: int,
                       artifact_brief: str = "",
                       month_scope: str = "all 12 months, January through December") -> str:
    """A compact PR-calendar prompt. Same output schema as the full template, but the elaborate
    METHOD (derive 3-6 narratives, build an opportunity bank across 3 classes, multi-step
    never-re-announce cross-check) is collapsed to a tight brief. Measured: the full prompt costs
    ~109s of model reasoning PER CALL regardless of how many stories it emits — that reasoning
    scaffolding, not output volume or story count, is the bottleneck. Trimming it is the only
    lever that moves the wall-clock."""
    objectives = "; ".join(taxonomy.DEFAULT_OBJECTIVES)
    grounding = render_grounding_context(_trim_bundle(grounding_bundle))
    brief = artifact_brief or "(No off-graph PR artifacts supplied — do not invent prior coverage.)"
    return f"""# ROLE
You are an enterprise PR strategist building part of a 12-month press-release calendar for
{brand_name} (planning year {year}). Ground EVERY story ONLY in the context below — never fabricate
facts, awards, dates, numbers or artifacts (mark ungrounded proof points "to source"). Do NOT browse
the web. Newsworthiness over promotion.

# GROUNDING CONTEXT (Odin CMG — the only source of business truth)
{grounding}

{brief}

# BUSINESS OBJECTIVES (tie each story to exactly one)
{objectives}

# TASK
Plan {month_scope}: TWO complementary stories per month — a `story_rank` 1 PRIMARY flagship (the
strongest, most newsworthy story that month can own) and a `story_rank` 2 SECONDARY (a distinct,
still-strong story, ideally a different narrative or opportunity type so the month isn't one-note),
both grounded in the context. For each: score 1-5 on Newsworthiness, Brand Relevance, Audience
Relevance, Media Potential, Timing; pr_score = the product of the five (High >= 1000, Medium 300-999,
Low < 300). Do NOT re-announce anything in the "already announced" list above (cite the url_key you
avoid in prior_coverage). Spread narratives across the months; prefer genuine news/thought-leadership/
data over promotion. Keep every free-text field to one tight line.

# OUTPUT — JSON only between the fences, nothing outside them
<<<PRCAL_JSON_START>>>
{{"brand": "{brand_name}", "year": {year},
  "narratives": [{{"name": "...", "authority": "why the brand can own it (grounded)"}}],
  "summary": "1-2 lines on the through-line of these months",
  "calendar": [
    {{"month": "January", "month_index": 1, "story_rank": 1,
      "title": "...", "story_type": "News announcement | Product launch | Thought leadership | Data story | Trend story | Partnership | Award | Event | Seasonal story | Destination story",
      "opportunity_type": "Brand | External | Newsjacking", "narrative": "...",
      "business_objective": "one of the objectives above", "audience": "primary audience",
      "news_hook": "what is genuinely new / why now", "brand_pov": "the POV the brand can own",
      "why_this_month": "grounded timing/seasonal/business rationale",
      "proof_points": ["grounded fact", "..."], "spokesperson": "role who can speak",
      "media_targets": ["Travel", "Luxury", "..."],
      "scores": {{"newsworthiness": 5, "brand_relevance": 5, "audience_relevance": 4, "media_potential": 4, "timing": 5}},
      "pr_score": 2000, "priority": "High", "intent": "Informational",
      "keywords": ["...", "...", "..."], "entities": ["real graph entities"], "grounding_nodes": ["graph:..."],
      "prompts": ["first-person AI-search question", "..."],
      "prior_coverage": [{{"url_key": "<real url_key or omit>", "relation": "avoids-reannouncing", "note": "..."}}]}}
    /* ...TWO stories (story_rank 1 primary, then 2 secondary) for every month in scope ({month_scope})... */
  ]}}
<<<PRCAL_JSON_END>>>
"""


def _parse(out: str) -> dict:
    candidates: list[str] = []
    m = _FENCE.search(out)
    if m:
        candidates.append(m.group(1))
    candidates += re.findall(r"```(?:json)?\s*(.*?)```", out, flags=re.DOTALL)
    if "{" in out and "}" in out:
        candidates.append(out[out.index("{"): out.rindex("}") + 1])
    for c in candidates:
        try:
            data = json.loads(c.strip())
            if isinstance(data, dict) and isinstance(data.get("calendar"), list):
                return data
        except Exception:
            continue
    raise ValueError(f"Could not parse the PR calendar JSON. Response began: {out[:200]!r}")


def _score_product(scores: dict) -> int:
    dims = ["newsworthiness", "brand_relevance", "audience_relevance", "media_potential", "timing"]
    prod = 1
    for d in dims:
        try:
            prod *= max(1, min(5, int(scores.get(d, 1))))
        except Exception:
            prod *= 1
    return prod


def _one_pass(brand_name, grounding_bundle, year, artifact_brief, model, scope, timeout, lean=True) -> dict:
    # allow_tools=False: the calendar is graph + artifact grounded and must NOT browse the
    # web — that keeps generation fast and bounded (no 15-min tool loops).
    # Uses the compact prompt (_build_fast_prompt): same schema, far less prompt scaffolding —
    # the leanest work we can hand the model for a grounded, scored, non-re-announcing calendar.
    out = generate.generate(
        _build_fast_prompt(brand_name, grounding_bundle, year, artifact_brief, month_scope=scope),
        model=model, timeout=timeout, allow_tools=False)
    return _parse(out)


# The year is generated as four QUARTERS in parallel. Each call stays small (3 months = 6
# stories), and four concurrent calls is the throughput sweet spot for the headless CLI
# before it starts queueing — so wall-clock ≈ one quarter instead of the sum of two big halves.
_QUARTERS = [
    "the months January–March (months 1–3 only)",
    "the months April–June (months 4–6 only)",
    "the months July–September (months 7–9 only)",
    "the months October–December (months 10–12 only)",
]


def generate_calendar(*, brand_name: str, grounding_bundle: dict[str, Any], year: int,
                      model: str = "haiku", artifact_brief: str = "", lean: bool = False) -> dict:
    """Generate + normalise the 12-month PR calendar. Runs the year as FOUR quarters **in
    parallel** on a fast model over a compact grounding bundle, so the whole calendar lands
    in roughly the time of a single quarter. `artifact_brief` is the off-graph source-material
    block so the plan never re-announces already-published stories and cites provenance.

    NOTE: `lean` (emit only picker/scoring fields, defer the full per-story brief to
    enrich_story() on select) was measured to give NO speedup — PR generation is bound by the
    per-story strategic reasoning (~20s/story), not by output tokens, so trimming fields doesn't
    move the wall-clock. It's kept off by default; the enrich_story() path stays available and
    is a no-op for already-complete stories."""
    import concurrent.futures as _cf
    parts: list[dict] = []
    with _cf.ThreadPoolExecutor(max_workers=len(_QUARTERS)) as ex:
        futs = [ex.submit(_one_pass, brand_name, grounding_bundle, year, artifact_brief, model, s, 300, lean)
                for s in _QUARTERS]
        for f in futs:
            try:
                parts.append(f.result())
            except Exception:  # noqa: BLE001 — a failed quarter is tolerated; the rest still fill the year
                pass
    cal = [it for p in parts for it in (p.get("calendar") or [])]
    if not cal:  # every quarter failed → single full pass as a fallback
        parts = [_one_pass(brand_name, grounding_bundle, year, artifact_brief, model,
                           "all 12 months, January through December", 900, lean)]
        cal = [it for p in parts for it in (p.get("calendar") or [])]
    data = {
        "brand": brand_name, "year": year,
        "narratives": next((p.get("narratives") for p in parts if p.get("narratives")), []),
        "summary": " ".join(p.get("summary", "") for p in parts if p.get("summary"))[:400],
        "calendar": cal,
    }
    # normalise: recompute score/priority defensively, group by month, keep the top
    # MAX_PER_MONTH per month by score, order months Jan→Dec, rank stories within a month.
    by_month: dict[int, list[dict]] = {}
    for item in cal:
        if not isinstance(item, dict):
            continue
        mi = item.get("month_index")
        if not isinstance(mi, int) or not (1 <= mi <= 12):
            name = (item.get("month") or "").strip().lower()
            mi = next((i + 1 for i, m in enumerate(_MONTHS) if m.lower() == name), None)
        if not mi:
            continue
        item["month_index"] = mi
        item["month"] = _MONTHS[mi - 1]
        scores = item.get("scores") or {}
        computed = _score_product(scores)
        if not isinstance(item.get("pr_score"), int) or item.get("pr_score", 0) <= 0:
            item["pr_score"] = computed
        item["priority"] = item.get("priority") or priority_of(item["pr_score"])
        by_month.setdefault(mi, []).append(item)

    def _score(s: dict) -> int:
        try:
            return int(s.get("pr_score") or 0)
        except Exception:
            return 0

    out_cal: list[dict] = []
    for i in range(1, 13):
        stories = sorted(by_month.get(i, []), key=_score, reverse=True)[:MAX_PER_MONTH]
        for rank, s in enumerate(stories, 1):
            s["story_rank"] = rank  # 1 = primary (highest-scored), 2 = secondary
            out_cal.append(s)
    data["calendar"] = out_cal
    if not data["calendar"]:
        raise ValueError("The PR calendar came back empty. Try regenerating.")
    return data


# fields the lean pass omits and enrich_story() fills in on demand
_ENRICH_FIELDS = ("brand_pov", "proof_points", "spokesperson", "media_targets", "keywords",
                  "entities", "grounding_nodes", "prior_coverage", "prompts", "intent")


def is_enriched(story: dict) -> bool:
    """True once a lean story has had its full brief generated (so we don't regenerate)."""
    return bool(story.get("_enriched")) or bool(story.get("proof_points") or story.get("keywords"))


def enrich_story(*, brand_name: str, grounding_bundle: dict[str, Any], story: dict,
                 artifact_brief: str = "", model: str = "haiku", year: int | None = None) -> dict:
    """Generate the FULL brief for a single selected story (the fields the lean calendar pass
    skipped). One small, fast, graph+artifact-grounded call. Returns the story merged with the
    enrichment; on any failure returns the story unchanged (the flow still works with essentials)."""
    grounding = render_grounding_context(_trim_bundle(grounding_bundle))
    brief = artifact_brief or "(No off-graph PR artifacts supplied.)"
    prompt = f"""# ROLE
You are an enterprise PR strategist writing the full brief for ONE already-chosen press-release
story for {brand_name}. Everything must be grounded in the context below — never fabricate facts,
awards, dates, numbers or artifacts. Do NOT browse the web.

# GROUNDING CONTEXT (Odin CMG — the only source of business truth)
{grounding}

{brief}

# THE CHOSEN STORY (already scheduled — do not change its title/month/scores)
Title: {story.get('title','')}
Month: {story.get('month','')}  ·  Story type: {story.get('story_type','')}  ·  Narrative: {story.get('narrative','')}
Business objective: {story.get('business_objective','')}
News hook: {story.get('news_hook','')}
Why this month: {story.get('why_this_month','')}

# TASK
Produce the full, grounded brief for this story. Ground every proof point in the context; if a
proof point isn't grounded, write it as "to source: ...". Check the source material and record any
prior artifacts this story builds on or must avoid re-announcing (by real url_key only).

# OUTPUT — JSON only, between the fences, nothing outside them
<<<PRCAL_JSON_START>>>
{{"brand_pov": "the point of view the brand can credibly own",
  "proof_points": ["grounded supporting fact", "..."],
  "spokesperson": "role who can speak (e.g. Executive Chef, GM)",
  "media_targets": ["Travel", "Luxury", "..."],
  "keywords": ["...", "...", "..."],
  "entities": ["real graph entities featured"],
  "grounding_nodes": ["graph:..."],
  "prompts": ["first-person AI-search question a reader would ask", "..."],
  "intent": "Informational",
  "prior_coverage": [{{"url_key": "<real url_key or omit>", "relation": "builds-on | avoids-reannouncing | aligns-voice", "note": "one line"}}]}}
<<<PRCAL_JSON_END>>>
"""
    try:
        out = generate.generate(prompt, model=model, timeout=180, allow_tools=False)
        m = _FENCE.search(out)
        raw = m.group(1) if m else (out[out.index("{"): out.rindex("}") + 1] if "{" in out else "{}")
        data = json.loads(raw.strip())
    except Exception:  # noqa: BLE001 — enrichment is best-effort; essentials already carry the flow
        return story
    if isinstance(data, dict):
        merged = dict(story)
        for k in _ENRICH_FIELDS:
            if data.get(k) not in (None, "", [], {}):
                merged[k] = data[k]
        merged["_enriched"] = True
        return merged
    return story


def calendar_markdown(data: dict) -> str:
    """Render the full 12-month calendar (every story, with grounding & reasoning) to
    Markdown — used for the 'download the calendar' action at the PR-calendar step."""
    brand = data.get("brand", "")
    year = data.get("year", "")
    lines = [f"# {brand} — 12-Month Press-Release Calendar ({year})", ""]
    if data.get("summary"):
        lines += [f"_{data['summary']}_", ""]
    narr = data.get("narratives") or []
    if narr:
        lines += ["## Strategic narratives", ""]
        for n in narr:
            auth = f" — {n.get('authority','')}" if n.get("authority") else ""
            lines.append(f"- **{n.get('name','')}**{auth}")
        lines.append("")
    ex = scoring_explainer()
    lines += ["## How the PR score is calculated", "",
              f"`{ex['formula']}`  ·  range {ex['range']}.", "",
              ex["why_multiplicative"], ""]
    for key, label, desc in ex["dimensions"]:
        lines.append(f"- **{label}** (1–5) — {desc}")
    lines += ["", "Priority bands: "
              + " · ".join(f"**{b}** {rng} ({note})" for b, rng, note in ex["bands"]), ""]
    consulted = data.get("_consulted") or []
    if consulted:
        lines += ["## Consulted source material (off-graph artifacts, read-only)", ""]
        for d in consulted:
            lines.append(f"- \"{d.get('title','')}\" ({d.get('date') or 'n.d.'}) — `url_key: {d.get('url_key','')}`")
        lines.append("")
    lines += ["---", ""]
    cur_month = None
    for item in data.get("calendar") or []:
        if item.get("month") != cur_month:
            cur_month = item.get("month")
            lines += ["", f"## {cur_month}", ""]
        rank = "Primary" if item.get("story_rank") == 1 else "Secondary"
        sc = item.get("scores") or {}
        lines += [
            f"### [{rank}] {item.get('title','')}",
            f"- **PR score:** {item.get('pr_score','—')} ({item.get('priority','—')}) — "
            + " · ".join(f"{label} {sc.get(k,'–')}" for k, label, _ in SCORE_DIMENSIONS),
            f"- **Type:** {item.get('story_type','—')} · {item.get('opportunity_type','—')}",
            f"- **Narrative:** {item.get('narrative','—')} · **Objective:** {item.get('business_objective','—')}",
            f"- **News hook:** {item.get('news_hook','—')}",
            f"- **Brand POV:** {item.get('brand_pov','—')}",
            f"- **Why this month (reasoning):** {item.get('why_this_month','—')}",
        ]
        if item.get("proof_points"):
            lines.append("- **Grounded proof points:** "
                         + "; ".join(str(p) for p in item["proof_points"]))
        if item.get("grounding_nodes"):
            lines.append("- **Grounding (graph nodes):** "
                         + ", ".join(str(g) for g in item["grounding_nodes"]))
        pc = item.get("prior_coverage") or []
        if pc:
            parts = []
            for p in pc:
                if isinstance(p, dict):
                    parts.append(f"{p.get('relation','ref')} → {p.get('url_key','')}"
                                 + (f" ({p.get('note','')})" if p.get("note") else ""))
                else:
                    parts.append(str(p))
            lines.append("- **Prior coverage (provenance):** " + "; ".join(parts))
        if item.get("spokesperson"):
            lines.append(f"- **Spokesperson:** {item['spokesperson']}")
        if item.get("media_targets"):
            lines.append("- **Media targets:** " + ", ".join(str(m) for m in item["media_targets"]))
        lines.append("")
    return "\n".join(lines)


def to_opportunity(item: dict) -> dict:
    """Map a selected month's PR story onto the standard opportunity record so it
    flows into the fan-out → generate → validate pipeline as a Press Release."""
    return {
        "id": f"pr-{item.get('month_index', 0):02d}-{item.get('story_rank', 1)}",
        "core_topic": item.get("title", ""),
        "industry": "Hospitality",
        "pillar_topic": item.get("narrative", "PR"),
        "keywords": item.get("keywords") or [],
        "prompts": item.get("prompts") or [],
        "intent": item.get("intent", "Informational"),
        "intent_reasoning": item.get("news_hook", ""),
        "reach": item.get("pr_score", "—"),
        "geo_lift": item.get("pr_score", "—"),
        "effort": "Medium",
        "entities": item.get("entities") or [],
        "memory_graph_nodes": {"entities": item.get("grounding_nodes") or []},
        "business_objective": item.get("business_objective", ""),
        "guest_journey": "Dreaming / Inspiration",
        "hotel_features": [],
        "content_gap_type": "Thematic",
        "recommendation": "Press Release",
        "confidence": "",
        "score": item.get("pr_score", 0),
        "evidence_sources": item.get("grounding_nodes") or [],
        "_raw": item,
    }
