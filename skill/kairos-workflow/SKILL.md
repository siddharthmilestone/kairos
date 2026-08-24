---
name: content-studio-workflow
description: >-
  Grounded, KAIROS-driven workflow to CREATE new content or OPTIMIZE an existing page for AI
  search (GEO/AIO/LLM) and E-E-A-T, for Milestone Internet's Odin-backed clients. Trigger when
  the user wants to create or improve a page/blog/article grounded in Odin, run the Content
  Studio workflow, turn a content opportunity into publishable content, or optimize a live URL
  to win AI citations. Chooses create vs optimize, grounds every fact in the Odin memory graph,
  runs live competitor research, generates, then KAIROS-scores and improves until it clears the
  publish bar, and stops at a human approval gate. Odin is read-only (no write-back).
---

# Project Kairos Workflow

Turn an Odin content opportunity into content that AI answer engines **cite** and humans trust —
either brand-new (**Create**) or by rewriting a live page (**Optimize**). This skill encodes the
validated workflow the Project Kairos runs; it composes three assets:

- **`geo-content-opportunity-engine`** — the ranked, Odin-grounded content opportunities (the topics).
- **`kairos-content-evaluator`** — the scoring model, Information-Gain method, gates, and (Mode D)
  the URL audit + rewrite for the Optimize branch.
- The business's **Odin memory graph** (via the `odin` CLI) — the only source of business facts.

## Non-negotiables (the goal)
1. **Grounding-first.** Every business-specific claim must trace to an Odin node or a cited
   high-authority public source. No invented facts, stats, quotes, awards, or numbers.
2. **Information Gain is the point.** Be the source a model would rather quote than paraphrase.
   Never optimize for keywords alone — optimize for knowledge quality and retrievability.
3. **Odin is read-only.** Do not write generated content back into the graph (no CMG write-back).
4. **Human approval gate.** On a passing score, prepare publish-ready output for a human to
   approve — never auto-publish.

## The workflow (both branches)

**Step 0 — Objective:** ask Create new content vs Optimize existing page.

**Step 1 — Build Context (Odin grounding):** resolve the business in Odin (`odin clients` →
`ODIN_CONTEXT_SCOPE=<id>/primary`, `ODIN_KIND=hospitality`) and pull grounding: brand, properties,
locations, review themes, keywords, business goals, schema types, GBP, plus semantic hits for the
topic (`search_entities_semantic`, `top_k`). Also capture brand voice + audience persona, and list
**first-party data to collect** that a great answer needs but Odin lacks.
- **Optimize also:** crawl the URL with a **headless browser + schema.org** extraction, then run a
  KAIROS **audit** of the current page — a baseline score and a **disposition**
  (retain / enhance / purge / consolidate).

**Step 2 — Discover Opportunity:**
- **Create:** select from the pre-computed `geo-content-opportunity-engine` opportunities.
- **Optimize:** auto-match the crawled page to the best-fit opportunities (term overlap on
  topic + keywords + entities + pillar) → shortlist → user picks.
- **Competitor Analysis (always live web research):** find the top 3–5 ranking pages and AI-answer
  results for the primary keyword; extract **missing topics** and **missing entities** to cover.

**Step 3 — Winning Strategy:** derive from the **full opportunity record** (see
`references/field-mapping.md`): `content_gap_type` → strategy, `geo_signals` → what to strengthen,
`recommendation` → format, `intent` → depth/CTA, `memory_graph_nodes`/`evidence_sources` →
entities & provenance. Plan both a **Visibility** strategy (SEO/GEO/AIO/LLM/E-E-A-T + retrieval
structure & schema) and a **Value-Addition** strategy (better examples, research, stats, expertise,
originality).

**Step 4 — Generate (grounding-first):** produce the content. Create = draft from the strategy;
Optimize = rewrite the audited page acting on every finding. No claim without an Odin node or a
cited high-authority source.

**Step 5 — Evaluate (KAIROS) & improve loop:** score with `kairos-content-evaluator`
(SEO, GEO, AIO, LLM-retrievability, Topic Coverage, Entity Coverage, **Information Gain**,
Hallucination-safety, Brand Compliance + gates). If any **gate fails** or overall < bar (≥80/100),
improve the weak areas and re-score. Cap at ~3 passes to avoid loops.

**Step 6 — Human approval gate:** present the publish-ready content + the KAIROS score/audit report
(Optimize: with disposition + before→after). A human approves before anything is published.
**No CMG write-back.**

## Phase 7 — Enterprise Validation & Certification (post-generation, independent audit)

After content exists, an **independent auditor pass** runs (it does NOT regenerate the content).
Grounded in Odin (or named high-authority sources), it produces four reports:

1. **Explainability** — paragraph-by-paragraph: why each block exists, the intent it serves, its
   position logic, its contribution to topical authority / E-E-A-T / SEO / GEO / AIO / LLM retrieval,
   which KAIROS principles it satisfies, evidence used, confidence, and grounding score.
2. **KAIROS whole-content validation** — the content architecture rationale plus a measured
   parameter scorecard (intent coverage, topical completeness, semantic clustering, entity
   optimisation, contextual relevance, E-E-A-T, search-intent alignment, visibility, retrieval,
   factual grounding, originality, readability, trustworthiness, overall quality).
3. **Competitive intelligence** — live top-5 competitor analysis and a prioritised, evidence-backed
   enhancement list (each with expected visibility / E-E-A-T / GEO-AIO-LLM impact + priority).
4. **Governance & certification** — a 150+ rule engine across weighted categories (Legal & IP,
   Regulatory & Claims, Privacy & Data, Accessibility WCAG 2.2 AA, Brand & Editorial, Lifecycle &
   Publishing, AI Governance, Security & Confidentiality, Risk & Ethics, Localisation) with
   Pass/Warning/Fail + severity + remediation + effort per rule, category scores, an overall
   Governance Score, Certification Status, Publication Readiness, Risk Rating, and content-level
   readiness for SOC 2 Type II, ISO 27001/27701/42001, GDPR, CCPA, HIPAA (if applicable), WCAG 2.2 AA.

Implemented by `prompts/enterprise_validation_prompt.md` + `lib/validation.py`; surfaced in the POC's
Review step as four tabs plus a downloadable **Certification Report PDF**. Odin stays read-only.

## Output (three parts, generation phase)
1. **Publish-ready content** — clean, paste-ready {format}: H1, intro, H2/H3 body, Key Takeaways,
   on-page FAQ, conclusion, CTA. No field labels or strategist commentary.
2. **Ops pack** — meta title/description/slug, schema types, internal/external links, image briefs,
   social assets.
3. **Score report & grounding notes** — KAIROS scores + gate pass/fail + improvement log +
   competitor research + (Optimize) current-state audit, disposition, before→after + grounding
   notes (which claims came from Odin) + "data to collect".

## Running it
- **Via the POC UI:** `kairos/run.sh` (the Streamlit wizard implements every step).
- **Headless:** the POC assembles `kairos/prompts/content_generation_prompt.md` (mode
  placeholders filled from the opportunity + inputs + Odin grounding + crawl snapshot) and runs it
  through `claude -p`, which performs the live web research, generation, and KAIROS score/improve
  loop, returning the three fenced sections.

See `references/field-mapping.md` for exactly how each opportunity-record field is used.
