"""KAIROS strategic reasoning shown on every step.

Concise, factual, bulleted, no superlatives. Explains what each step does and
why, in KAIROS terms. KAIROS = Knowledge · Authority · Intent · Retrieval ·
Originality · Structure.
"""
from __future__ import annotations

from typing import Any


def _opp(state: dict) -> dict:
    return state.get("selected_opp") or {}


def reason(step_key: str, state: dict[str, Any]) -> dict[str, Any]:
    mode = state.get("mode", "create")
    opp = _opp(state)

    if step_key == "objective":
        return {"title": "Choose the path", "pillars": ["Intent", "Originality"], "body":
                "Two paths, different work:\n\n"
                "- **Optimize**, improve a page that already exists; reuses its current indexing and authority.\n"
                "- **Create**, produce a new page for demand you don't yet cover.\n\n"
                "The steps that follow adapt to the path you pick."}

    if step_key == "output":
        return {"title": "Set format first", "pillars": ["Structure", "Retrieval"], "body":
                "Format determines how the answer is structured and retrieved:\n\n"
                "- How-To ordered steps + `HowTo` schema.\n"
                "- Comparison a table AI can extract directly.\n"
                "- FAQ-led self-contained Q&A + `FAQPage` schema.\n\n"
                "Setting it now aligns every later step. Language is set here so entities match the target market."}

    if step_key == "business":
        return {"title": "Ground in one business", "pillars": ["Knowledge", "Authority"], "body":
                "Selecting the Odin business points every fact at a real knowledge graph.\n\n"
                "- Grounds claims in verified entities (properties, amenities, reviews).\n"
                "- Prevents hallucinated or generic statements.\n"
                "- Grounding is a condition for AI systems to cite the page."}

    if step_key == "url":
        snap = state.get("crawl") or {}
        extra = ""
        if snap:
            extra = (f"\n\nExtracted **{snap.get('word_count','?')} words** of page copy via "
                     f"`{snap.get('fetch_method','')}`; schema: "
                     f"{', '.join(snap.get('schema_types', [])) or 'none'}.")
        return {"title": "Read the current page", "pillars": ["Retrieval", "Originality"], "body":
                "We extract the main content (navigation, header, footer and sidebars removed) to assess:\n\n"
                "- Duplication, does it repeat other pages?\n"
                "- Coverage gaps, what a complete answer needs but the page lacks.\n"
                "- Schema present on the page today." + extra}

    if step_key == "gentopics":
        return {"title": "Topics from the memory graph", "pillars": ["Knowledge", "Intent"], "body":
                "Opportunities are generated, not pulled from a fixed list:\n\n"
                "- Context comes from the Odin **Context Memory Graph (CMG)** for this business.\n"
                "- Generation is seeded by the crawled page, so topics extend it and fill its gaps.\n"
                "- Every topic is tied to real graph entities, no invented topics."}

    if step_key == "prcalendar":
        cal = state.get("pr_calendar") or {}
        extra = f"\n\n**{len(cal.get('calendar') or [])} months planned.**" if cal else ""
        return {"title": "PR calendar, not a content calendar", "pillars":
                ["Knowledge", "Authority", "Intent"], "body":
                "Strategy before scheduling, the year is built from the business, not a blank grid:\n\n"
                "- Narratives the brand can credibly own are derived from the Odin graph.\n"
                "- Each opportunity is scored on Newsworthiness × Brand fit × Audience × Media × Timing.\n"
                "- One newsworthy, grounded story lands per month, promotion scores lower than genuine news.\n"
                "- Pick a month to take that story into the press-release generation flow." + extra}

    if step_key == "plan":
        return {"title": "Decide before you build", "pillars": ["Originality", "Retrieval", "Knowledge"], "body":
                "The plan makes the optimization decision explicit before generation:\n\n"
                "- **Retain** what's accurate and citable, don't break what works.\n"
                "- **Enhance** thin sections with grounded facts and better structure.\n"
                "- **Prune** commoditised or off-intent passages that suppress citation.\n"
                "- **Create** the entities, questions, and blocks competitors have and this page lacks.\n\n"
                "Grounded in Odin + the live competitor landscape, you approve the intent before a word changes."}

    if step_key in ("match", "topic"):
        pillars = ["Intent", "Originality", "Retrieval"]
        if opp:
            gap = opp.get("content_gap_type", "-")
            gap_line = {
                "Structural": "Structural gap, restructure the page and add schema.",
                "Thematic": "Thematic gap, widen topic coverage to fully answer the intent.",
                "Critical": "Critical gap, an accuracy or authority issue to fix first.",
            }.get(gap, f"Gap type: {gap}.")
            lines = ["Why this topic:", ""]
            if mode == "optimize" and opp.get("match_score") is not None:
                lines.append(f"- Page match: {opp.get('match_score')}% term overlap.")
            lines.append(f"- {gap_line}")
            lines.append(f"- Scores, GEO Lift {opp.get('geo_lift','?')}/100, Reach {opp.get('reach','?')}/100.")
            lines.append(f"- Objective: {opp.get('business_objective','-')}.")
            lines.append("")
            lines.append("The **prompts** below are the questions users ask AI engines; each section must "
                         "answer one directly. **Entities** and **keywords** are relevance anchors to cover, "
                         "not terms to repeat.")
            body = "\n".join(lines)
        else:
            body = ("Pick the opportunity whose intent and gap fit your goal. Its keywords, entities, gap "
                    "type, and AI-search prompts are shown below.")
        return {"title": "Selecting the topic", "pillars": pillars, "body": body}

    if step_key == "fanout":
        fo = state.get("fanout") or {}
        cov = (fo.get("summary") or {}).get("answerability_coverage")
        extra = ""
        if fo:
            n = len(fo.get("queries") or [])
            extra = f"\n\n**{n} queries mapped.**" + (
                f" Page answerability: {cov}/100." if cov is not None else "")
        return {"title": "Map the query fan-out", "pillars": ["Intent", "Retrieval", "Knowledge"], "body":
                "AI search decomposes one question into many. This step maps that fan-out so the content "
                "answers the whole space, not just the headline query:\n\n"
                "- Each query is scored for **importance** and tagged by intent and decision stage.\n"
                "- For an existing page, each is judged **covered / partial / missing** on evidence.\n"
                "- The queries you approve become the answerability targets the generator must satisfy.\n\n"
                "This replaces relying on a fixed prompt list, it is the value-add over keyword tools."
                + extra}

    if step_key in ("preferences", "voice", "audience"):
        return {"title": "Set voice & audience once", "pillars": ["Authority", "Intent"], "body":
                "**Preferences** front-loads the two things that shape every later step:\n\n"
                "- **Brand voice** holds tone, claims, and vocabulary on-brand, consistency supports "
                "E-E-A-T (Authority & Trust).\n"
                "- **Audience** (persona + journey stage) sets depth, examples, and objections, matching "
                "intent is what makes content *the right answer*, not just on-topic.\n"
                "- Captured early, so topic selection and the fan-out can already account for the reader."}

    if step_key == "qa":
        return {"title": "Add first-party detail", "pillars": ["Originality", "Knowledge"], "body":
                "First-party facts raise Information Gain:\n\n"
                "- Adds specifics only the business knows and models can't invent.\n"
                "- Optional, skip and the workflow lists 'data to collect' instead."}

    if step_key == "cta":
        return {"title": "Tie content to an outcome", "pillars": ["Intent"], "body":
                "The CTA connects the page to a business objective:\n\n"
                "- Match the reader's stage, soft next step vs. direct action.\n"
                f"- Left blank, it is derived from the objective ({opp.get('business_objective','-')})."}

    if step_key == "generate":
        return {"title": "How generation runs", "pillars":
                ["Knowledge", "Authority", "Intent", "Retrieval", "Originality", "Structure"], "body":
                "The run proceeds in four stages:\n\n"
                "1. Pull grounding from the Odin CMG.\n"
                "2. Live competitor research, find missing topics and entities.\n"
                "3. Generate grounding-first, no claim without a graph node or cited source.\n"
                "4. KAIROS score and revise until the content clears the publish gates."}

    if step_key == "review":
        return {"title": "Gates and approval", "pillars": ["Authority", "Knowledge"], "body":
                "A passing score does not auto-publish:\n\n"
                "- You review the content and the KAIROS report.\n"
                "- Gates are hard fails, fabrication, unmet intent, or duplication block publish.\n"
                "- Odin is read-only; nothing is written back to the graph."}

    return {"title": "", "pillars": [], "body": ""}
