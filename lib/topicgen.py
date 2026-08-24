"""Generate a fresh set of ~30 Odin-grounded content opportunities on demand.

For the Optimize branch the generation is *seeded by the crawled page* so the
opportunities are directly relevant to (and gap-fill) that page — which makes
matching meaningful. Results are cached per business (+page) so repeat runs are
instant. Output conforms to the geo-content-opportunity-engine canonical schema.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from lib import generate, taxonomy
from lib.prompt import grounding_header, is_llm_bundle, render_grounding_context

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "_generated"
_FENCE = re.compile(r"<<<\s*TOPICS_JSON_START\s*>>>(.*?)<<<\s*TOPICS_JSON_END\s*>>>",
                    re.DOTALL | re.IGNORECASE)


def _cache_key(business_id: str, page_url: str | None) -> str:
    raw = f"{business_id}|{page_url or 'create'}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def cache_path(business_id: str, page_url: str | None) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tag = re.sub(r"[^a-z0-9]+", "-", business_id.lower()).strip("-")
    return CACHE_DIR / f"{tag}-{_cache_key(business_id, page_url)}.json"


def _trim_bundle(bundle: dict[str, Any], max_per_type: int = 6, max_ledger: int = 14) -> dict[str, Any]:
    """Lighten grounding for topic PLANNING. The generation step is dominated by the fixed
    cost of ingesting the prompt (a full grounding render is ~30KB → ~80s per call even for a
    handful of topics), so ideation gets a COMPACT bundle: each node keeps only its id, name
    and a couple of facts — the long descriptions, relations and provenance (the bulk of the
    render) are dropped, and counts are capped. This shrinks the prompt ~4x and is what makes
    topic generation land in a reasonable time. The full subgraph is still used for the actual
    content draft; ideation only needs entity breadth + a short fact ledger."""
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
                node = {"id": r.get("id", ""), "name": r.get("name", ""),
                        "type": r.get("type", "")}
                facts = r.get("facts") or {}
                if facts:  # keep at most 3 short facts; they anchor real specifics cheaply
                    node["facts"] = dict(list(facts.items())[:3])
                compact.append(node)
            out[k] = compact
        else:
            out[k] = v
    return out


def _build_prompt(business_name: str, grounding_bundle: dict[str, Any],
                  page_snapshot: dict[str, Any] | None, n: int, batch_note: str = "",
                  lean: bool = True) -> str:
    grounding = render_grounding_context(_trim_bundle(grounding_bundle))
    llm = is_llm_bundle(grounding_bundle)
    gc_header = grounding_header(grounding_bundle)
    known_from = ("you are researching from the public web (this business is NOT in Odin)"
                  if llm else "you know from the Odin memory graph")
    src_ref = ("the official website or a real, citable public source (use web: refs — never graph:)"
               if llm else "a real Odin node below (use graph: refs)")
    obj_src = ("infer them from the public business profile and the official website"
               if llm else "derive them from the `business_goal` nodes in the grounding context")
    value_policy = taxonomy.content_value_policy()
    output_schema = _output_schema(lean)
    objectives = "; ".join(taxonomy.DEFAULT_OBJECTIVES)
    journey = "; ".join(taxonomy.GUEST_JOURNEY)
    features = "; ".join(taxonomy.HOTEL_FEATURES)
    if page_snapshot:
        h = page_snapshot.get("headings", {})
        seed = f"""
# EXISTING PAGE TO OPTIMIZE (seed the opportunities around THIS page)

URL: {page_snapshot.get('url','')}
Title: {page_snapshot.get('title','')}
Meta: {page_snapshot.get('meta_description','')}
Schema present: {', '.join(page_snapshot.get('schema_types', [])) or 'none'}
H1/H2: {' | '.join(h.get('h1', []) + h.get('h2', [])[:12])}

Existing copy (full extracted page content):
```
{(page_snapshot.get('body_text','') or '')[:40000]}
```

Prioritise opportunities that (a) strengthen/extend this exact page, (b) fill
topical/entity/schema gaps it has, and (c) capture adjacent AI-search demand it
should own. Rank by relevance to this page first, then by opportunity score.
"""
        mode_line = ("You are finding content opportunities to OPTIMIZE and expand the specific "
                     f"page above for a business {known_from}.")
    else:
        seed = ""
        mode_line = f"You are finding net-new content opportunities for a business {known_from}."

    return f"""# ROLE
You are an enterprise GEO/AIO content strategist running the geo-content-opportunity-engine
methodology. {mode_line}

# HARD RULES (anti-fabrication)
Every factual claim must trace to {src_ref}. Never invent facts, stats, awards,
search volume, ratings, or numbers. Where a value is unknown use "Unknown"/"Not Available" and
lower `confidence`. `reach` and `geo_lift` are normalized 0-100 opportunity SCORES, never search
volume. **Work from the context above and your own knowledge — do NOT perform slow external web
browsing; this step is a fast planning pass.**

# {gc_header}
{grounding}
{seed}
{value_policy}
# TASK
Produce EXACTLY {n} ranked content opportunities for {business_name}, ordered by score
descending. {batch_note}Ground every opportunity in the context above. Apply the CONTENT VALUE POLICY
as a soft steer on the mix and on `score`: favour the high-value archetypes, avoid the low-value ones.
Move fast: dense, grounded opportunities, no filler.

Every opportunity MUST be mapped onto these FIXED hospitality frameworks (this vocabulary is
canonical — do NOT invent new labels; the Odin grounding informs *which* apply, not the wording):

- `business_objective`: EXACTLY ONE of these 10 canonical objectives (verbatim) — {objectives}.
  Pick the single objective the topic most directly advances. Emit the full list as
  `_meta.business_objectives`.
- `guest_journey`: EXACTLY ONE of these 35 lifecycle stages (verbatim) — {journey}.
  Pick the single stage where a guest would encounter/act on this content.
- `content_gap_type`: Structural | Thematic | Critical.
- `hotel_features`: 1–3 of these features, and ONLY those the relevant property actually offers per the
  grounding — {features}.

Spread the set across objectives and journey stages (aim to cover multiple of each; do not cluster
everything on one). Choose the objective/stage by fit to the topic — do not force an even distribution.

# OUTPUT — JSON only, between the fences, no prose outside them. Be TERSE: short strings, no
# prose padding. Do NOT restate the schema, do NOT add commentary before or after the fences.
{output_schema}

<<<TOPICS_JSON_START>>>
{{"_meta": {{"business": "{business_name}", "count": {n}, "seeded_by_page": {json.dumps(bool(page_snapshot))}}},
 "opportunities": [ ... {n} objects ... ]}}
<<<TOPICS_JSON_END>>>
"""


def _output_schema(lean: bool) -> str:
    if lean:
        # Lean schema: only the fields the picker + fan-out + generator actually consume.
        # Everything else (industry, pillar, intent_reasoning, entities, archetype,
        # confidence, location) is back-filled deterministically in opportunities.normalize,
        # so cutting it here roughly halves output tokens (the generation bottleneck).
        return (
            "Each opportunity object (snake_case) MUST include EXACTLY these fields and NOTHING else:\n"
            "id (kebab slug), core_topic (<=8 words), keywords (exactly 3),\n"
            "prompts (exactly 2, first-person AI-search questions),\n"
            "intent (Informational|Commercial|Transactional|Navigational|Local),\n"
            "reach (0-100), geo_lift (0-100), effort (Low|Medium|High),\n"
            "business_objective (one of the 10), guest_journey (one of the 35),\n"
            "hotel_features (array of 1-3), content_gap_type (Structural|Thematic|Critical),\n"
            "recommendation (Blog Article|News Article|Web Page|Listicle|How-To Article|etc),\n"
            "entities (3-6 REAL entity names taken from the grounding context — properties, "
            "amenities, locations, review themes, etc. that this topic is about; used to build the "
            "Context Memory Graph diagram, so they MUST be actual grounded nodes, never invented),\n"
            "memory_graph_nodes ({\"entities\":[the same real node names/ids],\"relations\":[2-4 "
            "\"NodeA -> relation -> NodeB\" edges between them from the grounding]}),\n"
            "evidence_sources (exactly 1 real graph:/web: ref), score (number)."
        )
    return (
        "Each opportunity object (snake_case) MUST include every field:\n"
        "id (kebab slug), core_topic, industry, pillar_topic, keywords (exactly 5),\n"
        "prompts (exactly 5, first-person AI-search questions), intent\n"
        "(Informational|Commercial|Transactional|Navigational|Local),\n"
        "intent_reasoning (1 sentence: WHY this intent), reach (0-100),\n"
        "geo_lift (0-100), effort (Low|Medium|High), location_city, location_country,\n"
        "memory_graph_nodes ({\"entities\":[real node ids/labels],\"relations\":[...]}),\n"
        "business_objective (one of the 10), guest_journey (one of the 35),\n"
        "hotel_features (array of 1-3),\n"
        "content_archetype (the closest HIGH-VALUE archetype from the CONTENT VALUE POLICY, verbatim),\n"
        "content_gap_type (Structural|Thematic|Critical), recommendation\n"
        "(Blog Article|News Article|Web Page|Listicle|How-To Article|LinkedIn Article|etc),\n"
        "confidence (0-100), evidence_sources (>=1 real graph:/web: refs), score (number)."
    )


def _one_batch(business_name, bundle, page_snapshot, nb, note, model) -> list[dict]:
    out = generate.generate(_build_prompt(business_name, bundle, page_snapshot, nb, batch_note=note),
                            model=model, timeout=240, allow_tools=False)
    return _parse_topics(out).get("opportunities") or []


def _plan_batches(n: int) -> list[tuple[int, str]]:
    """Split n topics into several small, concurrent batches. Generation is output-token
    bound (~a few seconds per opportunity), so many small batches that run in parallel beat
    one big serial call. We aim for ~6 topics per batch, biased across the 10 objectives so
    the batches stay distinct."""
    obj = taxonomy.DEFAULT_OBJECTIVES
    # Generation is model-reasoning bound (~a few seconds per grounded opportunity) and the
    # headless CLI parallelises to ~3-4 concurrent calls before it queues. So cap at 4 batches
    # and let each carry a handful of topics — 4 concurrent is the throughput sweet spot.
    nb = max(2, min(4, -(-n // 4)))  # ceil(n/4), clamped to 2..4 concurrent batches
    base, extra = divmod(n, nb)
    plan: list[tuple[int, str]] = []
    for i in range(nb):
        count = base + (1 if i < extra else 0)
        # rotate which objectives each batch leans into, so the set spreads across all 10
        lean_obj = obj[i::nb][:3] or obj[:3]
        note = (f"This is batch {i + 1} of {nb}. Lean toward these objectives: "
                + "; ".join(lean_obj)
                + ". Keep every topic DISTINCT from angles the other batches would obviously take. ")
        plan.append((count, note))
    return plan


def generate_topics(*, business_id: str, business_name: str, scope: str,
                    grounding_bundle: dict[str, Any],
                    page_snapshot: dict[str, Any] | None = None,
                    n: int = 30, model: str = "haiku",
                    use_cache: bool = True) -> tuple[Path, dict]:
    """Generate (or load cached) topics. Returns (json_path, parsed_dict).

    Speed: a lean output schema (only picker/fan-out/generator fields — the rest is
    back-filled in opportunities.normalize) over a light grounding bundle, split into
    several small batches that run in parallel on a fast model, so ~30 topics land in
    under a minute instead of several.
    """
    import concurrent.futures as _cf
    path = cache_path(business_id, page_snapshot.get("url") if page_snapshot else None)
    if use_cache and path.exists():
        try:
            return path, json.loads(path.read_text())
        except Exception:
            pass
    batches = _plan_batches(n)
    opps: list[dict] = []
    with _cf.ThreadPoolExecutor(max_workers=len(batches)) as ex:
        futs = [ex.submit(_one_batch, business_name, grounding_bundle, page_snapshot, nb, note, model)
                for nb, note in batches]
        for f in futs:
            try:
                opps += f.result()
            except Exception:  # noqa: BLE001 — a failed batch is tolerated; others still fill the set
                pass
    if not opps:  # every batch failed → one single pass so the user still gets topics
        opps = _one_batch(business_name, grounding_bundle, page_snapshot, n, "", model)
    # de-duplicate by core topic, cap at n
    seen, uniq = set(), []
    for o in opps:
        k = (o.get("core_topic") or "").strip().lower()
        if k and k not in seen:
            seen.add(k)
            uniq.append(o)
    if not uniq:
        raise ValueError("The model did not return any opportunities. Try regenerating.")
    data = {"_meta": {"business": business_name, "count": len(uniq[:n]),
                      "business_objectives": list(taxonomy.DEFAULT_OBJECTIVES)},
            "opportunities": uniq[:n]}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path, data


def _parse_topics(out: str) -> dict:
    """Robustly extract the topics JSON from a model response."""
    candidates: list[str] = []
    m = _FENCE.search(out)
    if m:
        candidates.append(m.group(1))
    # strip ```json fences
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", out, flags=re.DOTALL)
    candidates.extend(fenced)
    candidates.append(out)
    # from first { to last }
    if "{" in out and "}" in out:
        candidates.append(out[out.index("{"): out.rindex("}") + 1])
    for c in candidates:
        c = c.strip()
        if not c:
            continue
        try:
            data = json.loads(c)
            if isinstance(data, list):
                data = {"opportunities": data}
            if isinstance(data, dict) and "opportunities" in data:
                return data
        except Exception:
            continue
    raise ValueError("Could not parse the generated topics as JSON. "
                     f"Response began: {out[:200]!r}")
