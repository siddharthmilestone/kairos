# Project Kairos

Grounded, AI-optimized content intelligence - **KAIROS x Odin**. Project Kairos turns a
business's Odin memory-graph knowledge into publish-ready content that AI answer engines
will cite, with **every business fact traced to the graph** (no hallucination), then scores,
validates, and certifies the result.

- **Engine:** the local **Claude Code CLI** (`claude -p`, headless) - uses your Claude login, **no API key**.
- **Grounding:** the local **Odin CLI** (Context Memory Graph), read-only, Entra-authenticated.
- **Standard:** **KAIROS** = **K**nowledge, **A**uthority, **I**ntent, **R**etrieval, **O**riginality, **S**tructure.

---

## Install on your computer (Windows and Mac)

Kairos is a **desktop app** on each person's machine. Guide: **[INSTALL.md](INSTALL.md)**.

**Share the whole `kairos` folder** (zip or `git clone`). Do not send only
`Kairos.bat` / `Kairos.exe` — those files need `app.py`, `lib/`, `prompts/`, and
`scripts/` next to them. Skip `.venv` and `data/_cache` (recreated on each PC).

- **Windows:** double-click `Kairos.bat`. It installs Python 3.9+ if needed, then opens the app.
- **Mac:** `chmod +x Kairos.command`, then double-click `Kairos.command` (same Python auto-install).

Still required once per machine: **Odin** (`odin auth login`) and the **Claude Code CLI**
(`claude` then `/login`).

### Quick start (developers)

```bash
cd kairos
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium   # for the Optimize-path crawl
.venv/bin/python -m streamlit run app.py           # http://localhost:8501
```

---

## Three workflows (chosen by mode + format)

1. **Create** - generate brand-new content from a grounded Odin opportunity.
2. **Optimize** - paste a URL; the app crawls the real page, audits it, plans
   Retain/Enhance/Prune/Create, and rewrites it to win citations.
3. **Press Release Calendar** - pick the *Press Release Calendar* format; the app builds a
   grounded, KAIROS-scored **12-month PR calendar** (two scored stories per month), and any
   month flows into press-release generation.

### The wizard (steps adapt to the path)

```
Objective -> Format & Language -> CMG Business -> Preferences
  -> [Create]   Choose Topic
  -> [Optimize] Page URL -> Generate Topics -> Match Topic -> Optimization Plan
  -> [PR Cal]   PR Calendar
  -> Query Fan-Out -> Topic Q&A -> Call to Action -> Generate -> Review
```

---

## What each stage does

- **Choose Topic / Generate Topics** - grounded, faceted opportunities mapped onto the
  canonical 10 business objectives and 35 guest-journey stages; each carries real graph
  entities so the Context Memory Graph diagram can be drawn.
- **Preferences** - pick a **brand voice** and **audience persona**, both pre-generated from
  the business's grounding. The choices are enforced in every later step.
- **Query Fan-Out** - derives 5 original queries from the topic and fans each into the
  decision criteria an AI engine would explore, classified with the Qforia methodology
  (type, user intent, reasoning) plus white-space / click-worthiness scoring. You curate
  which to answer; they become the FAQ + answerability targets.
- **PR Calendar** - narratives -> opportunity bank -> PR scoring
  (`Newsworthiness x Brand x Audience x Media x Timing`) -> two scored stories per month.
- **Topic Q&A** - grounded, contextual questions that pull *first-party* detail the graph lacks.
- **Generate** - grounding-first writing with a KAIROS self-score/improve loop, then
  concurrently: per-paragraph validation, enterprise validation (KVE), and an enhancement advisor.
- **Review** - publish-ready content (clean, copy-paste-ready, no citation markup), the
  KAIROS scorecard, competitive intelligence, governance/certification, and the SEO ops pack.
  Export **PDF / Word / Markdown**.

---

## Grounding & anti-hallucination

- Every AI step injects the **Odin grounding bundle** (`odin.gather_grounding` ->
  `prompt.render_grounding_context`): core anchors + semantic seeds + 1-hop relation
  traversal, with a **verified fact ledger** (each atom carries provenance + freshness).
- Business facts may only come from that ledger; general knowledge needs a real, cited
  high-authority source (no invented URLs/stats/quotes/awards); missing facts are flagged
  "to source", never fabricated.
- A non-Odin business is grounded from its **public web profile** instead (the same render
  hook flips to public grounding); facts are cited to real public sources.
- An unauthenticated Odin session raises `OdinAuthError` (never silently treated as "no facts").

---

## Performance & caching

Every generation step (topics, brand voices, personas, fan-out, PR calendar, Q&A, content,
optimize plan) is cached to disk and shown with a "Generated <timestamp> / Regenerate"
control, so repeat runs and demos are instant. `scripts/prewarm.py` pre-generates the
business-level items (topics + voices + personas) for every Odin client:

```bash
.venv/bin/python scripts/prewarm.py        # all clients (add --force to regenerate)
```

Generation runs on Claude (`opus` default, `sonnet` / `haiku` selectable). Structured/planning
steps use a fast model automatically; only the final draft uses the model you pick.

---

## Architecture

```
kairos/
  app.py                 # Streamlit wizard: routing (ORDER_CREATE/OPTIMIZE/PRCAL), all step UIs
  requirements.txt · INSTALL.md
  setup.bat · Kairos.bat                # Windows (optional: scripts/build_windows_exe.bat → Kairos.exe)
  setup.sh · run.sh · Kairos.command    # Mac
  scripts/launch.py · scripts/kairos.spec
  lib/
    odin.py              # Odin CLI wrapper: auth/probe, clients, query, semantic search, deep grounding
    prompt.py            # builds the content prompt; render_grounding_context; format guidelines
    generate.py          # runs `claude -p` headless (transient-failure retry)
    generate_api.py      # optional Anthropic-API backend (KAIROS_MODEL_BACKEND=api)
    cache.py             # persistent, timestamped result cache
    topicgen.py          # grounded opportunity generation (+ entities for the CMG diagram)
    preferences.py       # grounded brand voices + audience personas
    taxonomy.py          # canonical objectives / journey / criteria + content-value policy
    opportunities.py     # load/normalize opportunity records
    crawl.py             # Optimize: Playwright + trafilatura crawl + JSON-LD schema
    matcher.py           # score topics vs crawled page
    optplan.py           # Retain / Enhance / Prune / Create plan
    fanout.py            # Qforia query fan-out engine (5 originals -> decision criteria)
    briefqa.py           # grounded first-party brief questions
    prcalendar.py        # 12-month PR calendar (scoring + to_opportunity mapping)
    artifacts.py         # read-only off-graph artifact consultation (prior PR releases)
    blockval.py          # per-paragraph validation
    validation.py        # enterprise validation (KVE): KAIROS + competitive + governance
    enhance.py           # enhancement advisor + inline apply
    reasoning.py         # per-step KAIROS reasoning cards
    docs.py              # brand-voice extraction, fence parsing, publish sanitizer, PDF/DOCX export
    ui.py                # design system, components, subgraph SVG
  prompts/               # the generation prompt templates the app assembles
  scripts/prewarm.py     # pre-generate topics + voices + personas for all Odin clients
  qa_static.py · qa_live.py   # QA suites (plumbing + live end-to-end)
```
