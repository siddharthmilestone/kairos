"""Assemble the final content-generation prompt from all workflow parameters.

Maps the selected opportunity + user inputs + Odin grounding onto the
{placeholders} in prompts/content_generation_prompt.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib import taxonomy

TEMPLATE = Path(__file__).resolve().parent.parent / "prompts" / "content_generation_prompt.md"


# =============================================================================
# Grounding source — Odin memory graph OR public web (LLM failsafe for non-Odin
# businesses). Every engine funnels grounding through render_grounding_context, so
# switching the bundle's source here flips the whole workflow to public-domain
# grounding with cited sources and no fabrication.
# =============================================================================
def public_bundle(profile: dict[str, Any]) -> dict[str, Any]:
    """A grounding bundle for a business that is NOT in Odin. Carries only the public
    identity; downstream code treats the `_`-prefixed keys as non-entity sentinels."""
    return {"_source": "llm", "_public_profile": dict(profile or {})}


def is_llm_bundle(bundle: Any) -> bool:
    return isinstance(bundle, dict) and bundle.get("_source") == "llm"


def _public_profile_block(p: dict[str, Any]) -> str:
    ptype = p.get("profile_type") or "Profile"
    lines = [
        f"Business: {p.get('name','')}",
        f"{ptype}: {p.get('profile_name','')}" if p.get("profile_name") else "",
        f"Official website: {p.get('url','')}" if p.get("url") else "",
        "",
        "This business is **NOT in the Odin memory graph** — there is no first-party graph to draw "
        "from. Ground EVERY business-specific claim in publicly available information: the official "
        "website above FIRST, then reputable public sources (established directories, review "
        "platforms, press, the brand's own channels). CITE the real source (URL or publication) for "
        "any specific fact, number, rating, award, or quote. Prefer facts verifiable on the official "
        "site or a high-authority source. If a fact cannot be verified publicly, write '[to verify]' "
        "rather than asserting it — NEVER invent names, amenities, numbers, ratings, awards, or quotes.",
    ]
    return "\n".join(x for x in lines if x != "" or True).strip() or "(no profile)"


def grounding_header(bundle: Any) -> str:
    if is_llm_bundle(bundle):
        return "PUBLIC BUSINESS PROFILE (no Odin graph — ground from public sources and cite them)"
    return "GROUNDING CONTEXT (from Odin — the ONLY source of business facts)"


_ODIN_CONTRACT = (
    "Every business-specific claim about **{brand_name}** (properties, amenities, dining, spa, "
    "locations, awards, offers, policies, numbers) MUST come from the GROUNDING CONTEXT below "
    "(the Odin memory graph). This is your only source of business truth.\n"
    "- Fact in GROUNDING CONTEXT → you may state it.\n"
    "- Fact NOT in GROUNDING CONTEXT and NOT general public knowledge → omit it or write "
    "'[not available in provided context]'.\n"
    "- General/public knowledge is allowed only when genuinely helpful AND, for any specific "
    "claim/stat/third-party fact, attributed to a real high-authority source. Never invent URLs "
    "or citations.\n"
    "- No invented numbers, ratings, review counts, ADR, or awards. No fabricated customer quotes.\n\n"
    "The GROUNDING CONTEXT is the FULL subgraph retrieved for this topic: entities, their facts "
    "(with provenance and freshness), AND the relationships between them. Use the relationships to "
    "connect entities and make sure the richest, most on-topic nodes are actually used. Track your "
    "sources internally by their [graph:id] for the grounding notes in PART C — but NEVER print "
    "[graph:...], [web:...], or any bracketed reference token in PART A: that is finished, "
    "reader-facing content and must read as clean prose with no citation markup."
)
_LLM_CONTRACT = (
    "This business is **not in the Odin memory graph** — you are grounding from the **public "
    "domain**. Every business-specific claim about **{brand_name}** MUST be grounded in publicly "
    "verifiable information and attributed to a real source.\n"
    "- Primary source of truth = the official website in the PUBLIC BUSINESS PROFILE below; use it "
    "for the brand's own facts (amenities, offers, locations, policies).\n"
    "- Any specific fact, number, rating, award, or quote → attribute it to a REAL public source "
    "(the official site or a high-authority publication) with the actual URL/name. NEVER invent a "
    "source, URL, statistic, award, or quote.\n"
    "- If a fact would strengthen the piece but cannot be verified publicly, write '[to verify]' or "
    "frame it as something the reader should confirm — do NOT assert it.\n"
    "- Well-established public knowledge about the destination/category is allowed, attributed when "
    "it is a specific claim.\n"
    "- Because there is no first-party graph, lean on the official website and cited public evidence, "
    "and be explicit about sourcing so the content stays trustworthy and citable."
)


def grounding_contract(bundle: Any, brand_name: str) -> str:
    t = _LLM_CONTRACT if is_llm_bundle(bundle) else _ODIN_CONTRACT
    return t.replace("{brand_name}", brand_name or "the brand")


def _semantic_keywords(opp: dict) -> list[str]:
    """Derive (never fabricate) semantic keywords from grounded fields:
    entity labels + pillar + geo_signal-flavored related phrases.
    """
    terms: list[str] = []
    terms.extend(opp.get("entities", []) or [])
    if opp.get("pillar_topic"):
        terms.append(opp["pillar_topic"])
    # secondary keywords (skip the primary) also seed the semantic set
    terms.extend((opp.get("keywords") or [])[1:])
    # dedupe preserving order, drop the primary keyword
    primary = (opp.get("keywords") or [None])[0]
    seen, out = set(), []
    for t in terms:
        t = (t or "").strip()
        if not t or t == primary or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t)
    return out[:12]


def render_grounding_context(bundle: dict[str, Any]) -> str:
    """Render the deep Odin grounding bundle into a citation-friendly block with
    facts, provenance, freshness, relations, and a sourced fact ledger.

    For a non-Odin (public-web / LLM) business, render the public profile + the
    ground-from-public contract instead — this single branch flips every engine
    (topics, fan-out, brief Q&A, generation, validation, PR calendar) to public
    grounding, since they all call this function."""
    if is_llm_bundle(bundle):
        return _public_profile_block(bundle.get("_public_profile") or {})
    if not bundle:
        return "(No Odin grounding context was retrieved. Do NOT assert business-specific facts.)"
    pretty = {
        "brand": "Brands", "property": "Properties", "resort": "Resorts", "hotel": "Hotels",
        "location": "Locations", "review_theme": "Guest Review Themes (verbatim reputation signals)",
        "keyword": "Tracked Keywords", "business_goal": "Business Goals",
        "business_problem": "Business Problems", "schema_type": "Schema Types Present",
        "google_business_profile": "Google Business Profiles", "web_page": "Existing Pages",
        "gap_analysis": "Gap Analyses",
        "author_first_party": ("Author First-Party Answers "
                               "(provided by the brand for this piece — authoritative, MUST be used)"),
    }
    lines: list[str] = []
    for etype, rows in bundle.items():
        if etype.startswith("_") or not rows:
            continue
        lines.append(f"### {pretty.get(etype, etype.replace('_', ' ').title())}")
        for r in rows:
            nid = r.get("id", "")
            name = r.get("name", nid)
            facts = r.get("facts") or {}
            fact_str = ("  {" + "; ".join(f"{k}: {v}" for k, v in facts.items()) + "}") if facts else ""
            meta = []
            if r.get("freshness"):
                meta.append(f"updated {r['freshness']}")
            if r.get("provenance"):
                meta.append(f"src: {r['provenance'][0]}")
            meta_str = ("  (" + "; ".join(meta) + ")") if meta else ""
            lines.append(f"- **{name}** [graph:{nid}]{fact_str}{meta_str}")
            desc = (r.get("description") or "").strip()
            if desc:
                lines.append(f"  {desc}")
            for rel in (r.get("relations") or [])[:10]:
                lines.append(f"  · {rel}")
        lines.append("")

    ledger = bundle.get("_fact_ledger") or []
    if ledger:
        lines.append("### Verified Fact Ledger (every atom is sourced; weigh by freshness & provenance)")
        for a in ledger[:160]:
            fresh = f" · updated {a['freshness']}" if a.get("freshness") else ""
            lines.append(f"- {a['fact']}  [graph:{a['source']}{fresh}]")
        lines.append("")
        lines.append("_Note: prefer fresher, provenance-backed facts; flag any that look inconsistent "
                     "rather than repeating them blindly._")
    return "\n".join(lines)


CREATE_MODE_BLOCK = (
    "**MODE: CREATE NEW CONTENT.** You are creating a brand-new {article_type} from scratch "
    "for the topic below. There is no existing page — build the strongest possible answer."
)
OPTIMIZE_MODE_BLOCK = (
    "**MODE: OPTIMIZE EXISTING CONTENT.** You are optimizing an already-published page "
    "(captured under EXISTING PAGE) to maximize AI citation and quality while preserving what "
    "works. First run a KAIROS audit of the existing page: score its current state, assign a "
    "**disposition** (retain / enhance / purge / consolidate), and list concrete weaknesses and "
    "missing entities. Then produce the optimized rewrite that acts on every finding. Re-fetch "
    "the URL yourself with full rendering if the snapshot looks thin."
)


def _existing_page_block(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return ""
    h = snapshot.get("headings", {})
    lines = [
        "# EXISTING PAGE (crawled snapshot — audit this before rewriting)",
        "",
        f"- URL: {snapshot.get('url','')}",
        f"- Fetch method: {snapshot.get('fetch_method','')}",
        f"- Title: {snapshot.get('title','')}",
        f"- Meta description: {snapshot.get('meta_description','')}",
        f"- Word count: {snapshot.get('word_count','?')}",
        f"- Schema.org types present: {', '.join(snapshot.get('schema_types', [])) or 'none detected'}",
        f"- H1: {' | '.join(h.get('h1', [])) or '(none)'}",
        f"- H2s: {' | '.join(h.get('h2', [])[:15]) or '(none)'}",
        f"- H3s: {' | '.join(h.get('h3', [])[:15]) or '(none)'}",
        "",
        "Existing body copy (full extracted page content):",
        "```",
        (snapshot.get("body_text", "") or "")[:60000],
        "```",
        "",
        "--------------------------------------------------",
        "",
    ]
    return "\n".join(lines)


def _fanout_block(queries: list[dict[str, Any]] | None, is_optimize: bool) -> str:
    """Render the approved decision-criteria fan-out as answerability targets, carrying the
    white-space / click-worthiness / scorecard signals so the writer produces information
    gain (not parity): answer white-space criteria with first-party evidence, and treat
    single-fact criteria as concise FAQ entries rather than deep sections."""
    if not queries:
        return "(No query fan-out supplied — infer the information needs from the topic and metadata.)"
    lines = [
        "These are the AI-search queries the editor approved, grouped under the **original query** each "
        "one fans out from. Each carries a **Qforia type**, the **user intent** it serves, and the "
        "**reasoning** for why a generative engine issues it — USE all three to answer it distinctively, "
        "not generically. Answer EACH one in a self-contained, directly-quotable way. Per item:",
        "- Honour the **Qforia type**: *Comparative Query* → give an extractable comparison (table or "
        "explicit criteria); *Implicit Query* → proactively answer the unstated need the user didn't ask; "
        "*Entity Expansion* → name and cover the specific entities; *Personalized Query* → tailor the "
        "answer to the stated persona/context; *Related Query* → cover the adjacent need fully; "
        "*Reformulation* → ensure the core answer is phrased so this wording also retrieves it.",
        "- Answer to the stated **user intent** (what the searcher actually wants at that step), and let "
        "the **reasoning** tell you what would make the answer win the citation.",
        "- **White space** (nobody has answered it) → highest-value target; answer with concrete "
        "first-party evidence (grounding + author answers). **Parity gap** → answer at least as "
        "specifically as competitors. **Single-fact** → short, exact FAQ-style answer, not a whole section.",
        "- Satisfy each item's **scorecard** (the specific facts a credible answer must contain — real "
        "numbers, named policies, dated specifics). Never fabricate; if a fact isn't grounded, say what "
        "would be needed rather than inventing it.",
        "",
    ]
    # group the selected queries under their original query so the writer answers each cluster coherently
    by_orig: dict[str, list[dict]] = {}
    order: list[str] = []
    for q in queries:
        ok = (q.get("original_query") or "General").strip()
        if ok not in by_orig:
            by_orig[ok] = []
            order.append(ok)
        by_orig[ok].append(q)
    for ok in order:
        lines.append(f"\n**Original query:** {ok}")
        for q in by_orig[ok]:
            pr = q.get("priority", q.get("importance", ""))
            parts = [f"[{pr}]" if pr != "" else "", f"**{q.get('query','')}**"]
            meta = []
            if q.get("qforia_type"):
                meta.append(str(q["qforia_type"]))
            for key in ("whitespace", "click_worthiness", "criteria_category", "type", "decision_stage"):
                if q.get(key):
                    meta.append(str(q[key]))
            if q.get("answerable_from"):
                meta.append(f"source: {q['answerable_from']}")
            if is_optimize and q.get("coverage"):
                meta.append(f"currently: {q['coverage']}")
            tail = f" ({' · '.join(meta)})" if meta else ""
            line = f"- {' '.join(p for p in parts if p)}{tail}"
            if q.get("user_intent"):
                line += f"\n    · user intent: {q['user_intent']}"
            if q.get("reasoning"):
                line += f"\n    · reasoning: {q['reasoning']}"
            need = q.get("information_need") or ""
            if need:
                line += f"\n    · need: {need}"
            sc = q.get("scorecard") or []
            if isinstance(sc, list) and sc:
                line += f"\n    · must contain: {'; '.join(str(s) for s in sc)}"
            lines.append(line)
    return "\n".join(lines)


_PRESS_RELEASE_GUIDELINES = (
    "# FORMAT GUIDELINES — PRESS RELEASE (AP style)\n\n"
    "Write a genuine, newsworthy press release — not a promotional blog. Structure:\n"
    "- **FOR IMMEDIATE RELEASE** at the very top.\n"
    "- **Headline** — a strong, factual news headline (no adjective-stacking, no hype).\n"
    "- **Subheadline** — one line adding the key supporting fact.\n"
    "- **Dateline** — City, Region — Month Day, Year — to open the lead paragraph.\n"
    "- **Lead paragraph** — the who / what / when / where / why in the first 2–3 sentences (inverted pyramid).\n"
    "- **Body** — supporting detail in descending importance: the news, the grounded proof points, context.\n"
    "- **At least two quotes** attributed to a named, plausible spokesperson role (e.g. General Manager, "
    "Executive Chef) — quotes must be substantive and grounded, never invented statistics.\n"
    "- **Boilerplate** — a short 'About {brand_name}' paragraph from the grounding.\n"
    "- **Media contact** — a placeholder block (Name / Title / email / phone as '[to supply]').\n"
    "- End with **###** (the standard end-of-release marker). No FAQ, no CTA-style marketing close.\n"
    "Newsworthiness over promotion: if the angle is purely promotional, reframe it around what is "
    "genuinely new or in the public interest."
)


# Per-format structure. Each block tells the writer the SHAPE this format must take, so the
# output reads like a real Blog Post / Landing Page / How-To / etc. - not a generic article.
# Shared, well-structured FAQ block — required on every long-form format (GEO/AEO retrieval
# loves clean Q&A). Rendered as its own H2 with each question an H3 so the UI can style it.
_FAQ_BLOCK = (
    "- **`## Frequently Asked Questions`** (required): 4-6 real questions the reader still has - "
    "draw them from the approved fan-out queries and genuine objections, not filler. Format each as "
    "its own `### <the question, ending in ?>` followed by a direct-answer-first reply of 40-90 words. "
    "Make every Q&A self-contained (name the subject, never 'it'/'this/'they') so an answer engine can "
    "lift it standalone. Order by what the reader most wants to know. Do NOT pad to a round number - "
    "quality over count.\n"
)

_FORMAT_GUIDES = {
    "blog article": (
        "# FORMAT - BLOG ARTICLE\n"
        "- **H1**: a specific, benefit-clear title (primary keyphrase used naturally, not forced).\n"
        "- **Opening (no heading, 2-3 sentences)**: lead with the direct answer or key takeaway to the "
        "reader's main question, then one line on why it matters. No throat-clearing.\n"
        "- **Body**: entity-rich, descriptive `## H2` sections (add `### H3` only where a section needs "
        "sub-parts). Each H2 answers one real reader question and stands on its own. Short paragraphs "
        "(<=90 words). Use bullet lists for collections and a table when comparing 3+ things.\n"
        "- Weave in concrete, grounded specifics (real names, numbers, policies from the grounding) - the "
        "detail competitors lack.\n"
        + _FAQ_BLOCK +
        "- **Close**: a genuine, useful last section ending on a concrete next step tied to the CTA. Never "
        "a 'Conclusion'/'Summary' heading."
    ),
    "listicle": (
        "# FORMAT - LISTICLE\n"
        "- **H1**: names the list and its value (e.g. 'X ways to ...', 'The N best ... for ...').\n"
        "- **Opening**: one short paragraph stating the **selection criteria** - why these items, how "
        "they were chosen. No filler intro.\n"
        "- **Each item = one `## H2`** (numbered or named). Keep formatting consistent across items: a "
        "one-line what-it-is, why it belongs / who it's for, and a concrete grounded detail. Every item "
        "must be materially useful - do NOT pad to hit a round number.\n"
        "- Use a short comparison **table** if the items share comparable attributes.\n"
        + _FAQ_BLOCK +
        "- **Close**: a one-paragraph how-to-choose, ending on the next step."
    ),
    "how-to guide": (
        "# FORMAT - HOW-TO GUIDE\n"
        "- **H1**: 'How to <accomplish the outcome>'.\n"
        "- **Opening**: state exactly what the reader will accomplish and, in one line, the end result.\n"
        "- **`## Before you start`**: prerequisites / what they need.\n"
        "- **`## Steps`**: numbered steps as `### Step 1: <action>` ... Each step: the action, a short "
        "explanation of why, and the expected outcome of that step. Do not omit steps to be shorter.\n"
        "- Call out **warnings / common mistakes** inline where they matter.\n"
        "- **`## Troubleshooting`** (only if useful): the 2-4 things most likely to go wrong + the fix.\n"
        + _FAQ_BLOCK +
        "- **Close**: the expected final result + a concrete next step. Consider `HowTo` schema in the ops pack."
    ),
    "comparison article": (
        "# FORMAT - COMPARISON ARTICLE\n"
        "- **H1**: 'X vs Y' (or 'Best ... compared').\n"
        "- **Opening**: the direct bottom-line-up-front answer (who should pick what), then the criteria "
        "you'll compare.\n"
        "- **`## How we compared`**: define the evaluation criteria FIRST, and apply the SAME criteria to "
        "every option.\n"
        "- **Comparison table**: options as columns (or rows), the shared criteria as the other axis - "
        "extractable at a glance.\n"
        "- **One `## H2` per option**: what it is, **who it's best for**, and its **limitations**. Make "
        "trade-offs explicit; never declare an unqualified 'winner' - frame it by use case.\n"
        + _FAQ_BLOCK +
        "- **Close**: a decision framework ('choose A if..., choose B if...') + next step."
    ),
    "landing page": (
        "# FORMAT - LANDING PAGE (conversion-focused, scannable)\n"
        "- **H1**: a sharp value proposition - the outcome the reader gets, not a feature list.\n"
        "- **Subhead (1-2 lines)**: who it's for + the core benefit, in plain language.\n"
        "- **Benefit sections**: 3-5 short `## H2` blocks, each a concrete benefit (not a feature dump), "
        "1-3 tight sentences or a short bullet list each. Lead with outcomes.\n"
        "- **Trust / proof**: include ONLY grounded, real proof (named amenities, awards, specifics from "
        "the grounding). Never invent testimonials, stats, or logos.\n"
        + _FAQ_BLOCK +
        "- **Primary CTA**: a clear, single next action aligned to intent, repeated once near the end. "
        "Persuasive but not hypey - no aggressive sales language. Keep the whole page tight and skimmable."
    ),
    "pillar page": (
        "# FORMAT - PILLAR PAGE (comprehensive hub)\n"
        "- **H1**: the broad topic this hub owns.\n"
        "- **Opening**: an answer-first overview of the whole topic + what the page covers.\n"
        "- **Major `## H2` subtopics**: each is self-contained and could stand as its own article; use "
        "`### H3` for the parts within. Cover the topic comprehensively and in logical order.\n"
        "- Note natural **internal-link opportunities** to deeper supporting articles (as descriptive "
        "anchor suggestions in the ops pack), where a subtopic deserves its own page.\n"
        "- Use tables/lists to organize breadth. Depth and authority matter here more than brevity, but "
        "every section must still earn its place.\n"
        + _FAQ_BLOCK +
        "- **Close**: where to go next (the key supporting pages) + the CTA."
    ),
    "thought leadership": (
        "# FORMAT - THOUGHT LEADERSHIP\n"
        "- **H1**: frames a clear point of view or thesis (not a generic topic label).\n"
        "- **Opening**: state the original argument / stance up front.\n"
        "- **Body `## H2` sections**: build the case with reasoning, industry context, and - most "
        "important - a genuine original element: a framework, first-hand/operational insight, or a "
        "grounded observation competitors don't have. Distinguish fact from informed opinion.\n"
        "- Support claims with grounded evidence; be confident but never exaggerate or use unsupported "
        "superlatives.\n"
        + _FAQ_BLOCK +
        "- **Close**: the forward-looking implication - what it means for the reader and what to do about it."
    ),
    "newsletter": (
        "# FORMAT - NEWSLETTER (personable, scannable)\n"
        "- **Subject-line + preview** belong in the ops pack; the body starts with a short, warm hook (1-2 "
        "sentences) that says why this issue is worth the reader's time.\n"
        "- **2-4 segments**, each a bolded lead-in (or short `## H2`) + a few useful sentences. Conversational "
        "and specific, not corporate. One clear idea per segment.\n"
        "- Include concrete, grounded specifics and, where natural, a link/next step per segment.\n"
        "- **Sign-off**: a brief, human close + one primary CTA. No FAQ, no keyword padding."
    ),
}


def format_guidelines(article_type: str, brand_name: str) -> str:
    at = (article_type or "").strip().lower()
    if at in ("press release", "press release calendar", "news article"):
        return _PRESS_RELEASE_GUIDELINES.replace("{brand_name}", brand_name or "the brand")
    return _FORMAT_GUIDES.get(at, "")


def _parse_qa_pairs(topic_qa: str) -> list[tuple[str, str]]:
    """Parse the 'Q: …\\nA: …' blocks the wizard stores into (question, answer) pairs."""
    pairs: list[tuple[str, str]] = []
    for chunk in (topic_qa or "").split("\n\n"):
        q = a = ""
        for ln in chunk.splitlines():
            s = ln.strip()
            if s.lower().startswith("q:"):
                q = s[2:].strip()
            elif s.lower().startswith("a:"):
                a = s[2:].strip()
        if a.strip():
            pairs.append((q, a))
    return pairs


def _author_answers_block(topic_qa: str) -> str:
    """Render the editor's first-party answers as an explicit, must-use checklist."""
    pairs = _parse_qa_pairs(topic_qa)
    if not pairs:
        return "(The editor did not provide first-party answers for this piece.)"
    lines = []
    for i, (q, a) in enumerate(pairs, 1):
        lines.append(f"{i}. Odin-derived question asked: {q or '(topic question)'}\n"
                     f"   AUTHOR'S FIRST-PARTY ANSWER TO INCLUDE: {a}")
    return "\n".join(lines)


def merge_author_answers(bundle: dict[str, Any], topic_qa: str) -> dict[str, Any]:
    """Fold the editor's first-party answers into the grounding bundle as sourced atoms.

    The answers become grounded facts (source = author first-party, in response to an
    Odin-derived question), so BOTH generation and the validation pass treat them as
    legitimate, citable grounding — not invented content. Idempotent.
    """
    pairs = _parse_qa_pairs(topic_qa)
    if not pairs:
        return bundle
    b = dict(bundle or {})
    if b.get("author_first_party"):  # already merged
        return b
    group, atoms = [], []
    for i, (q, a) in enumerate(pairs, 1):
        sid = f"author-first-party-{i}"
        group.append({
            "id": sid, "type": "author_first_party",
            "name": (q or f"Author answer {i}")[:90],
            "description": a, "facts": {}, "freshness": None,
            "provenance": ["author first-party answer (given in response to an Odin-derived question)"],
            "relations": [],
        })
        atoms.append({"fact": f"{a}", "source": sid,
                      "provenance": ["author first-party"], "freshness": None})
    b["author_first_party"] = group
    b["_fact_ledger"] = (b.get("_fact_ledger") or []) + atoms
    return b


def _enhancements_block(enh: list[dict[str, Any]] | None) -> str:
    if not enh:
        return "(none — first draft)"
    lines = []
    for e in enh:
        title = e.get("title") or e.get("label") or ""
        ins = e.get("insert") or e.get("why") or ""
        lines.append(f"- **{title}**" + (f" — {ins}" if ins else ""))
    return "\n".join(lines)


def build_prompt(opp: dict, *, mode: str = "create", brand_name: str, brand_voice: str,
                 article_type: str, target_audience: str, cta: str, topic_qa: str,
                 output_language: str, grounding_bundle: dict[str, Any],
                 crawl_snapshot: dict[str, Any] | None = None,
                 optimization_plan: str = "",
                 fanout_queries: list[dict[str, Any]] | None = None,
                 applied_enhancements: list[dict[str, Any]] | None = None,
                 artifact_brief: str = "") -> str:
    template = TEMPLATE.read_text()
    is_optimize = mode == "optimize"
    keywords = opp.get("keywords") or []
    primary = keywords[0] if keywords else opp.get("core_topic", "")
    secondary = keywords[1:] if len(keywords) > 1 else []

    # metadata JSON = full opportunity object + a compact business-metadata block
    metadata = {
        "opportunity": opp.get("_raw", opp),
        "business": {
            "brand_name": brand_name,
            "industry": opp.get("industry", ""),
            "primary_location": ", ".join(
                x for x in [opp.get("location_city"), opp.get("location_country")] if x),
            "schema_types_available": [
                r.get("name") or r.get("id")
                for r in grounding_bundle.get("schema_type", [])
            ],
        },
    }

    filled = {
        "{mode_block}": (OPTIMIZE_MODE_BLOCK if is_optimize
                         else CREATE_MODE_BLOCK.replace("{article_type}", article_type or "Blog")),
        "{format_guidelines}": format_guidelines(article_type, brand_name),
        "{artifact_brief}": artifact_brief or "",
        "{existing_page_block}": ((_existing_page_block(crawl_snapshot)
                                   + (f"\n# APPROVED OPTIMIZATION PLAN (execute this exactly)\n"
                                      f"The user has reviewed and approved this Retain / Enhance / "
                                      f"Prune / Create plan. Act on every item.\n\n{optimization_plan}\n\n"
                                      "--------------------------------------------------\n\n"
                                      if optimization_plan.strip() else ""))
                                  if is_optimize else ""),
        "{optimize_report_extra}": (
            "**Existing-page audit:** current-state KAIROS score, disposition "
            "(retain / enhance / purge / consolidate), and a before→after summary of key changes."
            if is_optimize else "(not applicable — new content)"),
        "{brand_name}": brand_name or "",
        "{grounding_contract}": grounding_contract(grounding_bundle, brand_name),
        "{grounding_header}": grounding_header(grounding_bundle),
        "{grounding_context}": render_grounding_context(grounding_bundle),
        "{article_type}": article_type or "Blog",
        "{article_topic}": opp.get("core_topic", ""),
        "{primary_keyword}": primary,
        "{secondary_keywords}": ", ".join(secondary) or "(none)",
        "{semantic_keywords}": ", ".join(_semantic_keywords(opp)) or "(derive from entities)",
        "{entities}": ", ".join(opp.get("entities", [])) or "(see opportunity metadata)",
        "{target_audience}": target_audience or "(general audience)",
        "{search_intent}": opp.get("intent", "Informational"),
        "{brand_voice}": brand_voice.strip() or ("(No brand-voice document provided — use the expert "
            "WRITING STYLE below as the voice: precise, confident, concrete, specific, no clichés, "
            "no adjective-stacking.)"),
        "{cta}": cta.strip() or f"(derive a CTA aligned to the business objective: {opp.get('business_objective') or 'drive direct bookings'})",
        "{strategic_fit}": (
            f"- **Business objective** this piece must advance: {opp.get('business_objective') or '—'}\n"
            f"- **Guest-journey stage** to write for: {opp.get('guest_journey') or '—'} "
            f"(lifecycle phase: {taxonomy.phase_of_journey(opp.get('guest_journey') or '')})\n"
            f"- **Relevant hotel features** (only what the property truly offers): "
            f"{', '.join(opp.get('hotel_features') or []) or '—'}\n"
            f"- **Content gap** being filled: {opp.get('content_gap_type') or '—'} · "
            f"**search intent**: {opp.get('intent') or 'Informational'}"),
        "{author_answers_block}": _author_answers_block(topic_qa),
        "{fanout_queries}": _fanout_block(fanout_queries, is_optimize),
        "{applied_enhancements}": _enhancements_block(applied_enhancements),
        "{output_language}": output_language or "English",
        "{metadata_json}": json.dumps(metadata, indent=2, ensure_ascii=False),
    }
    for k, v in filled.items():
        template = template.replace(k, str(v))
    return template
