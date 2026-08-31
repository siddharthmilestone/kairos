"""Project Kairos, grounded, KAIROS-driven create / optimize workflow.

Run:  ./run.sh   (or)   .venv/bin/streamlit run app.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import markdown2
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import (artifacts, blockval, briefqa, cache, crawl, docs, enhance, factcheck,  # noqa: E402
                 fanout, gates, generate, matcher, odin, opportunities, optplan, preferences,
                 prcalendar, prompt, readability, reasoning, runlog, schema_ld, taxonomy,
                 topicgen, ui, validation)

st.set_page_config(page_title="Project Kairos", page_icon="", layout="wide")
ui.inject_css()


def _passcode_from_secrets():
    """Read KAIROS_APP_PASSWORD from secrets.toml only if the file exists.

    Touching st.secrets with no file makes Streamlit paint a red
    'No secrets found' error even when the exception is caught.
    """
    roots = [Path(__file__).resolve().parent, Path.home()]
    if not any((root / ".streamlit" / "secrets.toml").is_file() for root in roots):
        return None
    try:
        return st.secrets.get("KAIROS_APP_PASSWORD")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — missing/empty secrets is the same as unset
        return None


def _require_passcode():
    """Optional shared-link access gate for self-hosting. If KAIROS_APP_PASSWORD is set
    (env var or .streamlit/secrets.toml), visitors must enter it before using the app.
    If it is not set, the app is open (no gate). This is an app-level passcode set by the
    host, not a user credential."""
    import os as _os
    pw = _os.environ.get("KAIROS_APP_PASSWORD") or _passcode_from_secrets()
    if not pw:
        return  # no passcode configured → open access
    if st.session_state.get("_authed"):
        return
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("<div style='height:14vh'></div>", unsafe_allow_html=True)
        st.markdown("### Project Kairos")
        st.caption("Enter the access passcode to continue.")
        entered = st.text_input("Passcode", type="password", label_visibility="collapsed",
                                placeholder="Access passcode")
        if entered:
            if entered == pw:
                st.session_state._authed = True
                st.rerun()
            else:
                st.error("Incorrect passcode.")
    st.stop()


_require_passcode()

LANGUAGES = ["English", "Spanish", "French", "German", "Portuguese", "Italian", "Japanese"]
FORMATS = ["Blog Article", "Newsletter", "Press Release", "Press Release Calendar",
           "How-To Guide", "Thought Leadership", "Comparison Article", "Landing Page",
           "Pillar Page", "Listicle", "News Article"]

LABELS = {
    "objective": "Objective", "output": "Format & Language", "business": "CMG Business",
    "preferences": "Preferences",
    "url": "Page URL", "gentopics": "Generate Topics", "match": "Match Topic",
    "plan": "Optimization Plan", "fanout": "Query Fan-Out", "prcalendar": "PR Calendar",
    "topic": "Choose Topic",
    "qa": "Topic Q&A", "cta": "Call to Action", "generate": "Generate", "review": "Review & Approve",
}
CTA_OPTIONS = [
    "Book your stay", "Check availability & rates", "Request a proposal",
    "Explore offers & packages", "Contact our concierge", "Plan your event",
]
# Preferences (brand voice + audience) is front-loaded right after Business, it's stable
# context set once, so capturing it before topic selection lets topics + fan-out use it.
ORDER_CREATE = ["objective", "output", "business", "preferences", "topic", "fanout", "qa",
                "cta", "generate", "review"]
ORDER_OPTIMIZE = ["objective", "output", "business", "preferences", "url", "gentopics", "match",
                  "fanout", "plan", "qa", "cta", "generate", "review"]
# Press Release Calendar: a create-style flow whose topic step is the 12-month calendar.
ORDER_PRCAL = ["objective", "output", "business", "preferences", "prcalendar", "fanout",
               "qa", "cta", "generate", "review"]


def ss(key, default):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


ss("step", 0)
ss("mode", None)
ss("grounding_source", "odin")  # "odin" (memory graph) | "llm" (public web, non-Odin business)


def is_llm() -> bool:
    """True when the run is powered by public-web/LLM grounding (non-Odin business)."""
    return st.session_state.get("grounding_source") == "llm"


def content_model() -> str:
    """The user's chosen model, used for the quality-critical final content draft,
    the enterprise validation (KVE), and inline Apply."""
    return st.session_state.get("model", "opus")


def fast_model() -> str:
    """Faster model for the many STRUCTURED / planning / validation steps (topics,
    fan-out, brief Q&A, PR calendar, per-paragraph validation, enhancement advisor,
    optimization plan). These emit JSON to a fixed schema, where Sonnet is materially
    faster than Opus with no meaningful quality loss, so planning never runs on the
    slow model, even if the user picked Opus for the final draft."""
    m = st.session_state.get("model", "opus")
    return "sonnet" if m == "opus" else m  # never use Opus for structured steps


def order() -> list[str]:
    if st.session_state.get("article_type") == "Press Release Calendar":
        return ORDER_PRCAL
    return ORDER_OPTIMIZE if st.session_state.get("mode") == "optimize" else ORDER_CREATE


def eff_type() -> str:
    """The format used for actual generation, a PR Calendar produces a Press Release."""
    at = st.session_state.get("article_type", "Blog Article")
    return "Press Release" if at == "Press Release Calendar" else at


def goto(i: int):
    st.session_state.step = max(0, min(i, len(order()) - 1))


def nav(back_ok=True, next_ok=True, next_label="Next", next_disabled=False):
    """Standardized bottom bar: Back on the far left, Next on the far right."""
    st.divider()
    left, _, right = st.columns([1.3, 4, 1.3])
    if back_ok and left.button("Back", key=f"back_{st.session_state.step}"):
        goto(st.session_state.step - 1)
        st.rerun()
    if next_ok and right.button(next_label, type="primary", disabled=next_disabled,
                                key=f"next_{st.session_state.step}"):
        goto(st.session_state.step + 1)
        st.rerun()


def header_chips() -> list[tuple[str, str]]:
    s = st.session_state
    chips: list[tuple[str, str]] = []
    if s.get("grounding_source") == "llm":
        chips.append(("Grounding", " Public web · LLM"))
    if s.get("mode"):
        chips.append(("Objective", "Create new" if s["mode"] == "create" else "Optimize existing"))
    if s.get("article_type"):
        chips.append(("Format", s["article_type"]))
    if s.get("output_language"):
        chips.append(("Language", s["output_language"]))
    if s.get("client"):
        chips.append(("Business" if is_llm() else "CMG Business", s["client"]["name"]))
    # Preferences (audience + brand voice), captured as one chip pair
    persona = s.get("target_audience", "")
    if persona and "segment:" in persona:
        seg = persona.split("segment:", 1)[1].split(",")[0].split(".")[0].strip()
        if seg:
            chips.append(("Audience", seg[:26]))
    if (s.get("brand_voice_text") or "").strip():
        chips.append(("Brand voice", "set "))
    if s.get("mode") == "optimize" and s.get("page_url"):
        u = s["page_url"].replace("https://", "").replace("http://", "").rstrip("/")
        chips.append(("Page", (u[:34] + "…") if len(u) > 35 else u))
    if s.get("selected_opp"):
        opp = s["selected_opp"]
        t = opp.get("core_topic", "")
        chips.append(("Topic", (t[:38] + "…") if len(t) > 39 else t))
        if opp.get("business_objective"):
            chips.append(("Objective ▸", opp["business_objective"][:30]))
        if opp.get("guest_journey"):
            chips.append(("Journey", opp["guest_journey"][:24]))
    if s.get("fanout_selected"):
        chips.append(("Fan-out", f"{len(s['fanout_selected'])} criteria"))
    if s.get("cta"):
        chips.append(("CTA", s["cta"]))
    return chips


def topic_detail(opp: dict, show_match: bool = False):
    st.markdown(f"#### {opp.get('core_topic','')}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("GEO Lift", opp.get("geo_lift", "-"))
    c2.metric("Reach", opp.get("reach", "-"))
    c3.metric("Confidence", opp.get("confidence", "-"))
    if show_match:
        c4.metric("Page match", f"{opp.get('match_score','-')}%")
    else:
        c4.metric("Score", opp.get("score", "-"))
    st.write(f"**Primary keyword:** {(opp.get('keywords') or ['-'])[0]}")
    kw = opp.get("keywords") or []
    st.write(f"**Secondary keywords:** {', '.join(kw[1:]) or '-'}")
    st.write(f"**Entities:** {', '.join(opp.get('entities') or []) or '-'}")
    # intent badge + generated reasoning
    st.markdown(
        f"**Search intent:** {ui.intent_badge(opp.get('intent'))}"
        f"<div style='background:#F8FAFC;border:1px solid #E5E7EB;border-left:3px solid #6B7280;"
        f"border-radius:8px;padding:8px 12px;margin:6px 0;font-size:12.8px;color:#374151;'>"
        f"<b style='color:#111827;'>Why this intent:</b> "
        f"{opp.get('intent_reasoning') or '-'}</div>",
        unsafe_allow_html=True)
    st.write(f"**Gap type:** `{opp.get('content_gap_type','-')}`  ·  "
             f"**Format rec:** {opp.get('recommendation','-')}  ·  "
             f"**Objective:** {opp.get('business_objective','-')}")
    prompts_list = opp.get("prompts") or []
    if prompts_list:
        st.markdown("**AI-search prompts this content must answer:**")
        for p in prompts_list:
            st.markdown(f"- {p}")
    if show_match and opp.get("matched_terms"):
        st.caption(f"Matched terms: {', '.join(opp['matched_terms'][:12])}")
    with st.expander("Full opportunity record (all metadata)"):
        st.json(opp.get("_raw", opp))


def render_topic_picker(records: list[dict], key_prefix: str, show_match: bool = False):
    """Nested/grouped accordion: 4 facet tabs, topics nested under each category value."""
    if not records:
        return
    sel = st.session_state.get("selected_opp") or {}
    sel_id = sel.get("id")
    st.caption(f"{len(records)} grounded topics, browse by category, expand a group, and select a topic.")
    with st.expander("How are these classified? (objectives · journey · gaps · features)", expanded=False):
        st.markdown(
            "- **Business Objective**, a **fixed framework** of 10 canonical hospitality objectives "
            "(not fetched from Odin). The AI maps each topic to the *one* objective it most directly "
            "advances, so the whole set ladders up to real business goals.\n"
            "- **Guest Journey**, a **fixed 35-stage lifecycle** (Dream  Book  Stay  Post-Stay). "
            "The AI places each topic at the stage a guest would actually encounter or act on it; the "
            "picker groups these into 6 lifecycle phases.\n"
            "- **Content Gaps**, identified by comparing what the **Odin graph** (and, in Optimize, the "
            "crawled page) already covers against live **AI-search demand**: a gap is where demand exists "
            "but grounded coverage doesn't (Critical / Thematic / Structural).\n"
            "- **Hotel Features**, read from the **Odin entity graph**, only the amenities/facilities the "
            "property actually has (suites, dining, spa, pools, weddings, MICE, kids, …).")
    with st.container(border=True):
        st.markdown("<div class='cs-eyebrow' style='margin:2px 0 0'>Browse Topics</div>",
                    unsafe_allow_html=True)
        tabs = st.tabs([label for _, label in taxonomy.FACETS])
        n = 0
        for (facet_key, _label), tab in zip(taxonomy.FACETS, tabs):
            with tab:
                groups = taxonomy.group_topics(records, facet_key)
                for value, recs in groups:
                    with st.expander(f"{value}  ·  {len(recs)} topic{'s' if len(recs) != 1 else ''}",
                                     expanded=False):
                        for r in recs:
                            n += 1
                            c1, c2 = st.columns([6, 1])
                            mtag = (f" · {r.get('match_score')}% match"
                                    if show_match and r.get("match_score") is not None else "")
                            mark = ("<span style='color:#5B5BD6;font-weight:700'>&#10003;</span> "
                                    if r["id"] == sel_id else "")
                            c1.markdown(
                                f"{mark}**{r['core_topic']}**  \n"
                                f"{ui.intent_badge(r.get('intent'))} "
                                f"<span style='color:#4B5563;font-size:12px'>{r['pillar_topic']}{mtag}</span>",
                                unsafe_allow_html=True)
                            if c2.button("Select", key=f"{key_prefix}_{n}"):
                                if (st.session_state.get("selected_opp") or {}).get("id") != r["id"]:
                                    for k in ("fanout", "fanout_selected", "fanout_sel_ids",
                                              "brief_pool", "brief_slots"):
                                        st.session_state.pop(k, None)
                                st.session_state.selected_opp = r
                                st.session_state._scroll_topic = True
                                st.rerun()
    opp = st.session_state.get("selected_opp")
    if opp:
        st.markdown("<div id='selected-topic'></div>", unsafe_allow_html=True)
        st.divider()
        st.markdown("### Selected Topic")
        topic_detail(opp, show_match=show_match)
        if st.session_state.pop("_scroll_topic", False):
            components.html(
                "<script>window.parent.document.getElementById('selected-topic')"
                "?.scrollIntoView({behavior:'smooth', block:'start'});</script>", height=0)


_STATUS_ICON = {"pass": "&#10003;", "warn": "!", "fail": "&#10007;"}  # check / bang / cross (no emoji)


_FAQ_HEAD_RE = re.compile(r"^\s{0,3}##\s+.*frequently asked question", re.I)
_H3_RE = re.compile(r"^\s{0,3}###\s+")
_H12_RE = re.compile(r"^\s{0,3}#{1,2}\s+")


def render_publish_blocks(blocks: list[dict], recs_by_idx: dict):
    """Render the publish-ready content block by block, but present the FAQ section as clean
    accordions (each question → an expander) instead of a wall of headings and paragraphs."""
    faq_mode = False
    for b in blocks:
        md_b = b["md"]
        first = md_b.lstrip().split("\n", 1)[0]
        is_h3 = bool(_H3_RE.match(first))
        rec = recs_by_idx.get(b["index"])

        # start of the FAQ section — render a styled header, then switch to accordion mode
        if _FAQ_HEAD_RE.match(first):
            faq_mode = True
            st.markdown(
                "<div class='cs-faq-head'>Frequently Asked Questions</div>"
                "<div class='cs-faq-sub'>The answers guests and AI engines look for, ready to lift.</div>",
                unsafe_allow_html=True)
            intro = re.sub(r"^\s{0,3}##\s+.*\n?", "", md_b, count=1).strip()
            if intro:
                st.markdown(intro)
            continue

        # a new H1/H2 ends the FAQ section
        if faq_mode and _H12_RE.match(first) and not is_h3:
            faq_mode = False

        if faq_mode and is_h3:
            question = re.sub(r"^\s{0,3}###\s+", "", first).strip().rstrip("?") + "?"
            answer = re.sub(r"^\s{0,3}###\s+.*\n?", "", md_b, count=1).strip()
            with st.expander(question):
                st.markdown(answer or "_(no answer generated)_")
                if rec:
                    with st.popover("ⓘ validation"):
                        render_block_popover(rec)
            continue

        c1, c2 = st.columns([28, 1])
        c1.markdown(md_b)
        with c2:
            with st.popover("ⓘ"):
                if rec:
                    render_block_popover(rec)
                else:
                    st.caption("No validation record for this block.")


_GATE_ICON = {"pass": "✓", "warn": "!", "fail": "✕"}


def preflight_gates(publish_md: str, opp: dict, article_type: str) -> dict:
    return gates.run_gates(
        publish_md, article_type=article_type,
        restricted_terms=(st.session_state.get("brand_safety") or {}).get("restricted_terms"),
        primary_keyword=(opp.get("keywords") or [""])[0] if opp.get("keywords") else "",
        output_language=st.session_state.get("output_language", "English"))


def render_quality_panel(pf: dict, opp: dict, client: dict):
    """Always-on, instant quality gates + readability + fact-check status + cannibalization.
    Runs deterministically the moment content exists (finding 13); the fact-check gate
    (finding 2) shows once validation has been run."""
    fc = st.session_state.get("factcheck")
    hard = pf["hard_pass"] and (fc is None or fc.get("gate_pass"))
    status_txt = "Ready to publish" if hard else "Needs attention before publishing"
    tone = "good" if hard else ("bad" if pf["failed"] or (fc and not fc.get("gate_pass")) else "warn")
    chips = "".join(
        f"<span class='cs-gate cs-gate-{g['status']}' title='{_esc_html(g['detail'])}'>"
        f"{_GATE_ICON.get(g['status'],'')} {_esc_html(g['label'])}</span>"
        for g in pf["gates"])
    fc_chip = ""
    if fc is not None:
        fcs = "pass" if fc.get("gate_pass") else "fail"
        fc_chip = (f"<span class='cs-gate cs-gate-{fcs}' title='{_esc_html(fc.get('summary',''))}'>"
                   f"{_GATE_ICON[fcs]} Fact-check gate</span>")

    with st.container(border=True):
        st.markdown(
            f"<div class='cs-qhead cs-q-{tone}'><span class='cs-qdot'></span>"
            f"<b>Pre-flight quality</b> · {status_txt}"
            f"<span class='cs-qmeta'>{pf['word_count']} words · "
            f"grade {pf['grade'] if pf['grade'] is not None else '—'} · "
            f"{pf['passed']} pass / {pf['warned']} warn / {pf['failed']} fail</span></div>"
            f"<div class='cs-gates'>{fc_chip}{chips}</div>", unsafe_allow_html=True)
        if fc is None:
            st.caption("Claim-level fact-check runs with **validation & scoring** below.")
        elif fc.get("unverified"):
            with st.expander(f"⚠ {len(fc['unverified'])} unverified claim(s) — review before publishing", expanded=False):
                for c in fc["unverified"]:
                    st.markdown(f"- {_esc_html(c.get('claim',''))}")

    canni = check_cannibalization(client, opp)
    if canni:
        items = "; ".join(f"“{_esc_html(c['topic'])}” ({c['overlap']}%)" for c in canni)
        st.warning(f"**Possible content overlap** with existing piece(s) for this client: {items}. "
                   "Consider differentiating the angle or consolidating to avoid competing for the "
                   "same queries.")


def render_block_popover(rec: dict):
    """Popover body: block score, 7-point data-findings checklist, CMG subgraph (inline SVG)."""
    score = rec.get("score")
    band = ("#1E6B3A" if (score or 0) >= 80 else "#8A6410" if (score or 0) >= 60 else "#9A2B2B")
    st.markdown(
        f"<div style='font-size:13px;color:#374151;margin-bottom:6px'>Paragraph validation</div>"
        f"<div style='font-size:26px;font-weight:700;color:{band};line-height:1'>"
        f"{score if score is not None else '-'}<span style='font-size:13px;color:#6B7280'> / 100</span></div>",
        unsafe_allow_html=True)
    # --- qualitative reasoning: why generated · memory-graph sources · coverage ---
    if rec.get("why"):
        st.markdown(f"<div style='margin-top:10px;font-size:12.5px;color:#374151'>"
                    f"<b style='color:#111827'>Why this was generated:</b> "
                    f"{_esc_html(rec['why'])}</div>", unsafe_allow_html=True)
    srcs = rec.get("sources") or []
    if srcs:
        chips = "".join(
            f"<span style='display:inline-block;font-size:10.5px;font-weight:600;color:#3730A3;"
            f"background:#EEF2FF;border:1px solid #E0E7FF;border-radius:6px;padding:2px 8px;"
            f"margin:3px 4px 0 0'>{_esc_html(s)}</span>" for s in srcs)
        st.markdown("<div style='margin:10px 0 2px;font-size:10.5px;font-weight:700;color:#6B7280;"
                    "text-transform:uppercase;letter-spacing:.5px'>Memory-graph sources referenced</div>"
                    f"<div>{chips}</div>", unsafe_allow_html=True)
    if rec.get("coverage"):
        st.markdown(f"<div style='margin-top:8px;font-size:12.3px;color:#475569'>"
                    f"<b style='color:#111827'>Knowledge coverage:</b> "
                    f"{_esc_html(rec['coverage'])}</div>", unsafe_allow_html=True)
    st.markdown("<div style='height:10px;border-top:1px solid #EDF1F5;margin-top:10px'></div>",
                unsafe_allow_html=True)
    checks = rec.get("checks") or {}
    rows = []
    for key in blockval.CHECKS:
        c = checks.get(key) or {}
        icon = _STATUS_ICON.get((c.get("status") or "").lower(), "•")
        rows.append(
            f"<div style='display:flex;gap:8px;padding:5px 0;border-top:1px solid #EDF1F5'>"
            f"<div style='flex:0 0 16px'>{icon}</div>"
            f"<div><b style='color:#111827;font-size:12.5px'>{blockval.CHECK_LABELS[key]}</b>"
            f"<div style='color:#475569;font-size:12px;line-height:1.45'>{_esc_html(c.get('note') or '-')}</div>"
            f"</div></div>")
    st.markdown("".join(rows), unsafe_allow_html=True)
    nodes = rec.get("cmg_nodes") or []
    st.markdown("<div style='font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;"
                "color:#6B7280;margin:12px 0 4px'>CMG nodes &amp; relationships</div>",
                unsafe_allow_html=True)
    if nodes:
        # inline SVG (no iframe) so it inherits the light theme and never renders dark
        st.markdown(f"<div style='background:#FFFFFF;border:1px solid #E5E7EB;border-radius:8px;"
                    f"padding:6px'>{ui.subgraph_svg(nodes, rec.get('cmg_relations') or [])}</div>",
                    unsafe_allow_html=True)
    else:
        st.caption("No CMG nodes cited for this block.")
    # --- untapped context for this block (graph entities not referenced here) ---
    used = {(n.get("label") or n.get("id") or "").lower() for n in nodes if isinstance(n, dict)}
    untapped = [nm for nm in _all_entity_names(st.session_state.get("grounding_bundle") or {})
                if nm.lower() not in used][:6]
    if untapped:
        chips = "".join(
            f"<span style='display:inline-block;font-size:11px;color:#3730A3;background:#EEF2FF;"
            f"border:1px solid #E0E7FF;border-radius:7px;padding:3px 9px;margin:4px 5px 0 0'>"
            f"● {_esc_html(nm)}</span>" for nm in untapped)
        st.markdown("<div style='margin:12px 0 2px;font-size:10.5px;font-weight:700;color:#6B7280;"
                    "text-transform:uppercase;letter-spacing:.5px'>Untapped context for this block</div>"
                    "<div style='font-size:11.5px;color:#4B5563;margin-bottom:4px'>Richer graph detail "
                    "this paragraph doesn't reference yet:</div>"
                    f"<div>{chips}</div>", unsafe_allow_html=True)


def _esc_html(s: str) -> str:
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _all_entity_names(bundle: dict) -> list[str]:
    names, seen = [], set()
    for etype, rows in (bundle or {}).items():
        if etype.startswith("_") or not isinstance(rows, list):
            continue
        for r in rows:
            nm = (r.get("name") or "").strip() if isinstance(r, dict) else ""
            if nm and len(nm) >= 3 and nm.lower() not in seen:
                seen.add(nm.lower())
                names.append(nm)
    return names


def whole_content_graph(block_records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Aggregate all per-block CMG nodes + relations into one whole-content graph."""
    nodes, seen_n = [], set()
    rels, seen_r = [], set()
    for rec in block_records or []:
        for n in rec.get("cmg_nodes") or []:
            if not isinstance(n, dict):
                continue
            key = (n.get("id") or n.get("label") or "").lower()
            if key and key not in seen_n:
                seen_n.add(key)
                nodes.append(n)
        for r in rec.get("cmg_relations") or []:
            if not isinstance(r, dict):
                continue
            key = f"{r.get('source','')}|{r.get('rel','')}|{r.get('target','')}".lower()
            if key.strip("|") and key not in seen_r:
                seen_r.add(key)
                rels.append(r)
    return nodes[:12], rels[:16]


def content_used_labels(block_records: list[dict]) -> list[str]:
    """Labels/ids of CMG nodes each paragraph actually cited (to highlight in the graph)."""
    out = []
    for rec in block_records or []:
        for n in rec.get("cmg_nodes") or []:
            if isinstance(n, dict):
                v = n.get("label") or n.get("id") or ""
                if v:
                    out.append(str(v))
    return out


def bundle_graph(bundle: dict, used_labels: list[str]):
    """Turn the actual Odin grounding bundle into (nodes, relations, total, used_count).

    This is the FULL retrieved subgraph fed to generation, every entity type and the
    traversed 1-hop relations, not just what the validator echoed per paragraph.
    """
    used = {u.lower() for u in (used_labels or [])}
    nodes, rels, seen = [], [], set()
    for etype, rows in (bundle or {}).items():
        if etype.startswith("_") or not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            nid = str(r.get("id") or r.get("name") or "")
            lab = str(r.get("name") or nid).strip()
            if not lab or lab.lower() in seen:
                continue
            seen.add(lab.lower())
            is_used = lab.lower() in used or (nid and nid.lower() in used)
            relations = r.get("relations") or []
            nodes.append({"id": nid or lab, "label": lab, "type": etype,
                          "used": is_used, "_deg": len(relations)})
            for rel in relations:
                if isinstance(rel, str) and " → " in rel:
                    rn, tgt = rel.split(" → ", 1)
                    rels.append({"source": nid or lab, "rel": rn.strip(), "target": tgt.strip()})
    total = len(nodes)
    used_count = sum(1 for n in nodes if n["used"])
    # prioritise for display: cited first, then highest relation degree, then by type
    nodes.sort(key=lambda n: (not n["used"], -n["_deg"], n["type"]))
    return nodes[:46], rels, total, used_count


def _replace_publish(md: str, new_body: str) -> str:
    """Splice a revised publish-content body back into the full generated markdown."""
    import re as _re
    pat = _re.compile(r"(<<<PUBLISH_CONTENT_START>>>)(.*?)(<<<PUBLISH_CONTENT_END>>>)", _re.DOTALL)
    if pat.search(md):
        return pat.sub(lambda m: m.group(1) + "\n" + new_body.strip() + "\n" + m.group(3), md)
    return new_body  # defensive: no fence found


def validate_suite(content, opp, client, bundle, model, at, lang):
    """Run block validation + enterprise validation + enhancement advisor concurrently."""
    import concurrent.futures as _cf
    blocks = docs.split_blocks(content)

    def _bv():  # structured validation  fast model
        return blockval.run(blocks=blocks, brand_name=client["name"],
                            brand_voice=st.session_state.get("brand_voice_text", ""),
                            target_audience=st.session_state.get("target_audience", ""),
                            opportunity=opp, grounding_bundle=bundle, model=fast_model())

    def _kve():  # enterprise validation  user's model (quality + web)
        return validation.run_validation(publish_content=content, brand_name=client["name"],
                                         article_type=at, output_language=lang,
                                         grounding_bundle=bundle, opportunity=opp, model=model)

    def _enh():  # advisor  fast model
        return enhance.run(content=content, brand_name=client["name"], opportunity=opp,
                           fanout_queries=st.session_state.get("fanout_selected") or [],
                           grounding_bundle=bundle, model=fast_model())

    def _fc():  # claim-level fact verification (hallucination hard gate)
        return factcheck.run(publish_content=content, brand_name=client["name"],
                             grounding_bundle=bundle, model=fast_model())

    with _cf.ThreadPoolExecutor(max_workers=4) as ex:
        fbv, fkve, fenh, ffc = ex.submit(_bv), ex.submit(_kve), ex.submit(_enh), ex.submit(_fc)
        return fbv.result(), fkve.result(), fenh.result(), blocks, ffc.result()


def render_enhancements(bundle: dict, content: str, client: dict, model: str):
    """Untapped-context chips + Apply (surgical in-place rewrite) / Dismiss suggestion cards."""
    enh = st.session_state.get("enhancements") or []
    dismissed = set(st.session_state.get("dismissed_enh") or [])

    st.markdown("##### Untapped context")
    untapped = enhance.untapped_entities(bundle, content)
    if untapped:
        st.markdown("<div style='font-size:13px;color:#4B5563;margin-bottom:6px'>Your memory graph holds "
                    "richer detail on this topic that the draft doesn't reference yet:</div>"
                    + "".join(f"<span class='cs-ent'>● {_esc_html(n)}</span>" for n in untapped),
                    unsafe_allow_html=True)
    else:
        st.caption("The draft already references the available graph entities.")

    st.markdown("##### Recommended enhancements")
    st.caption("**Apply** rewrites the content in place to fold the suggestion in; the scores then need "
               "a quick re-validate (button appears above).")
    actionable = [e for e in enh if e.get("id") not in dismissed]
    if not enh:
        st.caption("No enhancement suggestions were produced for this draft.")
    elif not actionable:
        st.caption("All suggestions have been applied or dismissed.")
    for e in actionable:
        imp = (e.get("impact") or "Medium")
        with st.container(border=True):
            st.markdown(
                f"<div class='cs-enh-t'>{_esc_html(e.get('title',''))} "
                f"<span class='cs-imp {imp.lower()}'>Impact · {imp}</span></div>"
                f"<div class='cs-enh-row'><span class='k'>Why</span>"
                f"<span class='v'>{_esc_html(e.get('why',''))}</span></div>"
                f"<div class='cs-enh-row'><span class='k'>Impact</span>"
                f"<span class='v'>{_esc_html(e.get('impact_note',''))}</span></div>"
                + (f"<div class='cs-enh-row'><span class='k'>Add</span>"
                   f"<span class='v'>{_esc_html(e.get('insert',''))}</span></div>"
                   if e.get("insert") else ""),
                unsafe_allow_html=True)
            a, d, _ = st.columns([1, 1, 5])
            if a.button(" Apply", key=f"enh_ap_{e['id']}", type="primary"):
                md = st.session_state.get("generated_md", "")
                cur_pub = docs.split_sections(md).get("publish_content", "")
                try:
                    with st.spinner(f"Rewriting to incorporate “{e.get('title','')}”…"):
                        new_pub = enhance.apply_one(
                            content=cur_pub, suggestion=e, brand_name=(client or {}).get("name", ""),
                            grounding_bundle=bundle, model=model)
                except Exception as ex:  # noqa: BLE001
                    st.error(f"Apply failed: {ex}"); new_pub = ""
                if new_pub and new_pub.strip() and new_pub.strip() != cur_pub.strip():
                    st.session_state.generated_md = _replace_publish(md, new_pub)
                    st.session_state.content_blocks = docs.split_blocks(new_pub)
                    st.session_state.enhancements = [x for x in enh if x.get("id") != e["id"]]
                    st.session_state.setdefault("applied_log", []).append(e.get("title", ""))
                    st.session_state.validation_stale = True
                    st.rerun()
                elif new_pub:
                    st.warning("The edit came back unchanged, try again or Dismiss.")
            if d.button("Dismiss", key=f"enh_di_{e['id']}"):
                dismissed.add(e["id"])
                st.session_state.dismissed_enh = list(dismissed)
                st.rerun()

    log = st.session_state.get("applied_log") or []
    if log:
        st.divider()
        st.markdown("**Applied edits:** " + " · ".join(f" {_esc_html(t)}" for t in log))


_COV_COLOR = {
    "Fully Covered": ("#065F46", "#D1FAE5"), "Contextually Covered": ("#065F46", "#D1FAE5"),
    "Partially Covered": ("#92400E", "#FEF3C7"), "Unsupported": ("#991B1B", "#FEE2E2"),
    "Contradicted": ("#991B1B", "#FEE2E2"), "Not Applicable": ("#475569", "#F1F5F9"),
}
# 3-bucket white-space colours: white space = the prize (green), parity = amber, answered = grey
_WS_COLOR = {
    "White space": ("#065F46", "#D1FAE5"), "Parity gap": ("#92400E", "#FEF3C7"),
    "Answered": ("#475569", "#F1F5F9"),
}


def _pill(text: str, fg: str, bg: str) -> str:
    return (f"<span style='display:inline-block;font-size:10.5px;font-weight:700;color:{fg};"
            f"background:{bg};border-radius:6px;padding:1px 7px;margin-left:6px'>{_esc_html(text)}</span>")


def render_fanout(fo: dict, has_page: bool):
    """Scorecard + curatable, importance-ranked query list grouped by decision stage."""
    queries = fo.get("queries") or []
    summ = fo.get("summary") or {}
    ws = fanout.whitespace_summary(queries)
    cols = st.columns(4)
    cols[0].metric("Criteria mapped", len(queries))
    cols[1].metric(" White space", ws.get("White space", 0),
                   help="Decision criteria answered by NO ONE, where information gain lives. "
                        "Pre-selected as the highest-value targets.")
    if has_page:
        cov = summ.get("answerability_coverage")
        cols[2].metric("Page answerability", f"{cov}/100" if cov is not None else "-")
        csum = fanout.coverage_summary(queries)
        gaps = (csum.get("Unsupported", 0) + csum.get("Partially Covered", 0)
                + csum.get("Contradicted", 0))
        cols[3].metric("Gaps to close", gaps)
    else:
        cols[2].metric("Parity gaps", ws.get("Parity gap", 0),
                       help="Answered by a competitor but not you, the old kind of gap.")
        cols[3].metric("Fast-FAQ (single-fact)", summ.get("faq_only", sum(1 for q in queries if q.get("faq_only"))),
                       help="Single-fact criteria an AI fully resolves, routed to concise FAQ answers, "
                            "not deep sections (Click-Worthiness gate).")

    htype = summ.get("hospitality_type")
    if htype:
        st.markdown(f"<div style='font-size:12px;color:#475569;margin:2px 0 6px'>Criteria weighted for a "
                    f"<b>{_esc_html(htype)}</b> property.</div>", unsafe_allow_html=True)
    if summ.get("fanout_rationale"):
        st.markdown(f"<div class='cs-forationale'><b>Why this fan-out:</b> "
                    f"{_esc_html(summ['fanout_rationale'])}</div>", unsafe_allow_html=True)
    st.caption("Each item is a **decision criterion** a guest must have validated to trust the answer. "
               " white-space and high-priority criteria are pre-selected; single-fact items sit under "
               "**Fast-FAQ** (they feed the FAQ, not deep sections). Priority = Opportunity × Competition "
               "× Click-Worthiness. Your selection becomes the answerability target for generation.")
    b1, b2, _ = st.columns([1, 1.2, 4])
    if b1.button("Select all"):
        for q in queries:
            st.session_state[f"foq_{q['id']}"] = True
        st.rerun()
    if b2.button("High-value only"):
        hv = set(fanout.default_selected_ids(queries))
        for q in queries:
            st.session_state[f"foq_{q['id']}"] = q["id"] in hv
        st.rerun()

    _QF_COLOR = {
        "Reformulation": ("#475569", "#F1F5F9"), "Related Query": ("#0F766E", "#ECFDF5"),
        "Comparative Query": ("#9A3412", "#FFF7ED"), "Implicit Query": ("#3730A3", "#EEF2FF"),
        "Entity Expansion": ("#7C2D12", "#FEF3C7"), "Personalized Query": ("#831843", "#FCE7F3"),
    }

    def _row_detail(q: dict):
        """The retained rich signals for one query, shown in a per-row popover."""
        imp = q.get("priority", q.get("importance", 0))
        band = fanout.importance_band(imp)
        rows = [f"<div class='rz'><b>Priority:</b> {band} {imp} "
                f"(Opportunity {q.get('opportunity','-')} x Competition [{_esc_html(q.get('whitespace','-'))}] "
                f"x Click-worthiness [{_esc_html(q.get('click_worthiness','-'))}])</div>"]
        tags = " · ".join(x for x in [q.get("criteria_category", ""), q.get("criteria_scope", ""),
                                      f"family: {q.get('type','')}" if q.get("type") else "",
                                      q.get("decision_stage", ""),
                                      f"source: {q.get('answerable_from','')}" if q.get("answerable_from") else ""]
                          if x)
        if tags:
            rows.append(f"<div class='rz'><b>Criteria:</b> {_esc_html(tags)}</div>")
        if has_page and q.get("coverage"):
            fg, bg = _COV_COLOR.get(q["coverage"], ("#475569", "#F1F5F9"))
            pct = q.get("coverage_pct")
            rows.append(f"<div class='rz'><b>Page coverage:</b> <span class='cs-cov' "
                        f"style='background:{bg};color:{fg}'>{q['coverage']}"
                        f"{(' · ' + str(pct) + '%') if pct is not None else ''}</span>"
                        + (f" - {_esc_html(q.get('evidence_note',''))}" if q.get("evidence_note") else "")
                        + "</div>")
        sc = q.get("scorecard") or []
        if isinstance(sc, list) and sc:
            rows.append(f"<div class='rz'><b>A credible answer must contain:</b> "
                        f"{_esc_html('; '.join(str(s) for s in sc))}</div>")
        if q.get("outperforms"):
            rows.append(f"<div class='rz'><b>Outperforms:</b> {_esc_html(q['outperforms'])}</div>")
        comp = q.get("top_competitor") or {}
        serp = q.get("serp_estimate")
        if (isinstance(comp, dict) and comp.get("name")) or serp:
            nm = _esc_html(comp.get("name", "")) if isinstance(comp, dict) else ""
            comp_html = (f"<a href='{_esc_html(comp['url'])}' target='_blank'>{nm}</a>"
                         if isinstance(comp, dict) and comp.get("url") else (nm or "-"))
            tail = f" · {_esc_html(serp)}" if serp else ""
            label = "Your rank" if q.get("serp_source") else "Ranking now"
            rows.append(f"<div class='rz'><b>{label}:</b> {comp_html}{tail}</div>")
        if q.get("serp_results"):
            top3 = " · ".join(f"{r.get('position')}. {_esc_html(r.get('domain',''))}"
                              for r in q["serp_results"][:3])
            rows.append(f"<div class='rz'><b>Live SERP:</b> {top3}</div>")
        if q.get("recommendation"):
            rows.append(f"<div class='rz'><b>Recommendation:</b> {_esc_html(q['recommendation'])}</div>")
        st.markdown("".join(rows), unsafe_allow_html=True)

    def _table_header():
        h = st.columns([0.5, 4.2, 1.9, 2.6, 3.6])
        for col, lbl in zip(h, ["", "Fan-Out Query", "Type", "User Intent", "Reasoning"]):
            col.markdown(f"<div style='font-size:10.5px;font-weight:700;color:#6B7280;"
                         f"text-transform:uppercase;letter-spacing:.4px'>{lbl}</div>",
                         unsafe_allow_html=True)

    def _render_row(q: dict):
        qid = q["id"]
        st.session_state.setdefault(f"foq_{qid}", False)
        c = st.columns([0.5, 4.2, 1.9, 2.6, 3.6])
        c[0].checkbox("", key=f"foq_{qid}", label_visibility="collapsed")
        badges = ""
        if q.get("whitespace"):
            fg, bg = _WS_COLOR.get(q["whitespace"], ("#475569", "#F1F5F9"))
            badges += _pill(q["whitespace"], fg, bg)
        if q.get("faq_only"):
            badges += _pill("Fast-FAQ", "#475569", "#F1F5F9")
        if q.get("answerable_from") == "First-party needed":
            badges += _pill("First-party", "#3730A3", "#EEF2FF")
        c[1].markdown(f"<div class='cs-foqq'>{_esc_html(q.get('query',''))}</div>{badges}",
                      unsafe_allow_html=True)
        fg, bg = _QF_COLOR.get(q.get("qforia_type", ""), ("#475569", "#F1F5F9"))
        c[2].markdown(f"<span class='cs-qf' style='background:{bg};color:{fg}'>"
                      f"{_esc_html(q.get('qforia_type') or '-')}</span>", unsafe_allow_html=True)
        c[3].markdown(f"<div class='cs-fometa'>{_esc_html(q.get('user_intent') or '-')}</div>",
                      unsafe_allow_html=True)
        c[4].markdown(f"<div class='cs-fometa'>{_esc_html(q.get('reasoning') or '-')}</div>",
                      unsafe_allow_html=True)
        # popover (not expander) — the row already sits inside the per-original accordion,
        # and Streamlit forbids nesting an expander inside an expander.
        with c[4].popover("Signals & evidence"):
            _row_detail(q)

    st.caption("Grounded in the topic's **5 original queries** below; each is fanned out into the "
               "decision criteria an AI engine would explore. Every fan-out query is classified with "
               "one **Qforia type**, one **user intent**, and one **reasoning** (Mike King methodology). "
               "White-space and high-priority criteria are pre-selected; your ticked rows (with their "
               "type, intent and reasoning) become the answerability targets for generation.")

    # one accordion per original query — collapsed keeps the step calm; first opens by default
    for gi, group in enumerate(fanout.group_by_original(fo), 1):
        o = group["original"]
        qs = group["queries"]
        if not qs:
            continue
        n_sel = sum(1 for q in qs if st.session_state.get(f"foq_{q['id']}"))
        label = (f"Original {gi} · {o.get('query','')} · {len(qs)} quer"
                 f"{'y' if len(qs) == 1 else 'ies'}" + (f" · {n_sel} selected" if n_sel else ""))
        with st.expander(label, expanded=(gi == 1)):
            if o.get("intent"):
                st.markdown(f"<span class='cs-qf' style='background:#EEF2FF;color:#3730A3'>"
                            f"{_esc_html(o['intent'])}</span>", unsafe_allow_html=True)
            _table_header()
            for q in qs:
                _render_row(q)


def collect_fanout_selection(fo: dict):
    queries = fo.get("queries") or []
    selected = [q for q in queries if st.session_state.get(f"foq_{q['id']}")]
    st.session_state.fanout_sel_ids = [q["id"] for q in selected]
    st.session_state.fanout_selected = selected


def _seed_fanout_selection(data: dict):
    """Pre-tick the high-value default selection for a freshly loaded/generated fan-out."""
    ids = fanout.default_selected_ids(data.get("queries") or [])
    st.session_state.fanout_sel_ids = ids
    for q in data.get("queries") or []:
        st.session_state[f"foq_{q['id']}"] = q["id"] in ids


def _pref_grounding(llm: bool, client: dict | None, pp: dict, biz_name: str) -> dict:
    """Grounding for building the presets, public profile for a non-Odin business, else a
    light Odin bundle (reused from session if already fetched for this business)."""
    if llm:
        return prompt.public_bundle(pp)
    b = st.session_state.get("grounding_bundle")
    if not b:
        b = get_grounding(f"{client['id']}/primary", biz_name, light=True)
        st.session_state.grounding_bundle = b
    return b


def get_preferences(client: dict | None, *, regenerate: bool = False):
    """Get-or-generate the grounded brand voices + personas for a business, via the persistent
    cache. Returns (options, generated_at). Shared shape with the pre-warm script so a
    pre-generated business shows instantly. `client` None (or is_llm) uses the public profile."""
    llm = is_llm()
    pp = st.session_state.get("public_profile") or {}
    biz_name = (pp.get("name") if llm else (client or {}).get("name")) or ""
    biz_id = (pp.get("name") if llm else (client or {}).get("id")) or ""
    if not biz_name:
        return None, None
    ck = cache.key(biz_id)
    if not regenerate:
        data, ts = cache.load("prefs", ck)
        if data:
            return data, ts
    bundle = _pref_grounding(llm, client, pp, biz_name)
    opts = preferences.generate_preferences(business_name=biz_name, grounding_bundle=bundle,
                                            model="haiku")
    ts = cache.save("prefs", ck, opts)
    return opts, ts


def _apply_pref(kind: str, name: str, text: str):
    if kind == "voice":
        st.session_state.brand_voice_text = text
        st.session_state.brand_voice_name = name
    else:
        st.session_state.target_audience = text
        st.session_state.persona_name = name


def _pref_picker(kind: str, items: list[dict]):
    """One dropdown (presets + 'Write my own') with a live preview card beneath it."""
    text_key = "voice" if kind == "voice" else "persona"
    name_key = "brand_voice_name" if kind == "voice" else "persona_name"
    label = "Brand Voice" if kind == "voice" else "Audience Persona"
    names = [it["name"] for it in items]
    CUSTOM = " Write my own"
    options = names + [CUSTOM]
    cur = st.session_state.get(name_key)
    idx = names.index(cur) if cur in names else (len(options) - 1 if cur == "Custom" else 0)
    st.markdown(f"<div class='cs-fieldlabel'>{label}</div>", unsafe_allow_html=True)
    choice = st.selectbox(label, options, index=idx, key=f"pref_sel_{kind}",
                          label_visibility="collapsed")
    if choice == CUSTOM:
        seed = st.session_state.get("brand_voice_text" if kind == "voice" else "target_audience", "")
        seed = seed if st.session_state.get(name_key) == "Custom" else ""
        txt = st.text_area(f"Describe your {text_key}", value=seed, height=130,
                           key=f"pref_custom_{kind}",
                           placeholder=("Tone, vocabulary, point of view, what to avoid…" if kind == "voice"
                                        else "Who they are, what they value, their objections, decision stage…"))
        _apply_pref(kind, "Custom", txt.strip())
    else:
        it = items[names.index(choice)]
        _apply_pref(kind, it["name"], it.get(text_key, ""))
        with st.container(border=False):
            if it.get("summary"):
                st.markdown(f"<div class='cs-prefsum'>{_esc_html(it['summary'])}</div>",
                            unsafe_allow_html=True)
            st.markdown(f"<div class='cs-prefbody'>{_esc_html(it.get(text_key,''))}</div>",
                        unsafe_allow_html=True)


def render_preferences():
    st.markdown("<p class='cs-lede'>Choose a <b>brand voice</b> and an <b>audience persona</b>, "
                "pre-built for this business. Your picks are written into every later step, so the "
                "final content adheres to them.</p>", unsafe_allow_html=True)

    client = st.session_state.get("client")
    biz_name = ((st.session_state.get("public_profile") or {}).get("name")
                if is_llm() else (client or {}).get("name")) or ""
    if not biz_name:
        st.info("Select a business first (the **CMG Business** step) to load its voices and personas.")
        return

    opts, ts = st.session_state.get("pref_options"), st.session_state.get("pref_options_ts")
    if opts is None:  # try the persistent cache first (pre-warmed businesses are instant)
        opts, ts = cache.load("prefs", cache.key((client or {}).get("id") or biz_name))
        st.session_state.pref_options, st.session_state.pref_options_ts = opts, ts

    action = ui.gen_status_bar(
        has_data=bool(opts), generated_at=ts, key="prefs",
        generate_label="Generate brand voices & personas",
        busy_hint="~1 minute · grounded in this business")
    if action in ("generate", "regenerate"):
        with st.status("Building brand voices and personas…", expanded=True) as status:
            try:
                opts, ts = get_preferences(client, regenerate=(action == "regenerate"))
                st.session_state.pref_options, st.session_state.pref_options_ts = opts, ts
                status.update(label="Ready", state="complete")
                st.rerun()
            except odin.OdinAuthError as e:
                st.session_state.odin_conn = {"ok": False, "needs_reauth": True, "message": str(e)}
                status.update(label="Odin sign-in needed", state="error"); st.error(str(e))
            except Exception as e:  # noqa: BLE001
                status.update(label="Generation failed", state="error"); st.error(str(e))

    if not opts:
        st.caption("Not generated yet for this business. Click **Generate** above, or pick from the "
                   "pre-built set once it's ready.")
        return

    voices = opts.get("brand_voices") or []
    personas = opts.get("personas") or []
    c1, c2 = st.columns(2, gap="large")
    with c1:
        _pref_picker("voice", voices)
    with c2:
        _pref_picker("persona", personas)

    _render_author_safety(opts, biz_name)


def _render_author_safety(opts: dict, biz_name: str):
    """E-E-A-T author identity + brand-safety guardrails (findings 8 & 11), editable, with
    grounded defaults. Both flow into generation and the JSON-LD."""
    a = st.session_state.get("author") or opts.get("author") or {}
    bs = st.session_state.get("brand_safety") or opts.get("brand_safety") or {}
    with st.expander("Author & brand safety  ·  E-E-A-T", expanded=False):
        st.markdown("<div class='cs-fieldlabel'>Author (E-E-A-T) — appears as byline & in schema</div>",
                    unsafe_allow_html=True)
        ac1, ac2 = st.columns(2)
        name = ac1.text_input("Author name", value=a.get("name") or f"{biz_name} Editorial Team",
                              key="author_name_in")
        title = ac2.text_input("Author title / role", value=a.get("title") or "Editorial Team",
                               key="author_title_in")
        bio = st.text_area("Author bio (credibility, first-hand expertise)", value=a.get("bio") or "",
                           height=72, key="author_bio_in",
                           placeholder="e.g. Two decades hosting guests on-property; writes from direct experience.")
        st.session_state.author = {"name": name.strip(), "title": title.strip(), "bio": bio.strip()}

        st.markdown("<div class='cs-fieldlabel' style='margin-top:10px'>Brand safety — hard guardrails</div>",
                    unsafe_allow_html=True)
        rt = st.text_input("Restricted terms (comma-separated) — never used in content",
                           value=", ".join(bs.get("restricted_terms") or []), key="brand_rt_in",
                           placeholder="cheap, world-class, guaranteed, competitor names…")
        dis = st.text_area("Required disclaimers (one per line) — included where relevant",
                           value="\n".join(bs.get("required_disclaimers") or []), height=72,
                           key="brand_dis_in", placeholder="Rates are subject to availability.")
        st.session_state.brand_safety = {
            "restricted_terms": [t.strip() for t in rt.split(",") if t.strip()],
            "required_disclaimers": [d.strip() for d in dis.splitlines() if d.strip()],
        }


def render_pr_calendar(cal: dict):
    """12-month calendar grid (1 scored story/month) + selected-story detail."""
    if cal.get("summary"):
        st.markdown(f"<div class='cs-forationale'><b>Calendar strategy:</b> "
                    f"{_esc_html(cal['summary'])}</div>", unsafe_allow_html=True)
    narr = cal.get("narratives") or []
    if narr:
        chips = "".join(f"<span class='cs-ent'>{_esc_html(n.get('name',''))}</span>" for n in narr)
        st.markdown("<div style='font-size:10.5px;font-weight:700;color:#6B7280;text-transform:"
                    "uppercase;letter-spacing:.5px;margin-bottom:5px'>Strategic narratives</div>"
                    + chips, unsafe_allow_html=True)
    st.markdown("##### 12-month press-release calendar")
    st.caption("**Two grounded, scored stories per month** (a primary flagship + a complementary "
               "secondary). Expand any story for its grounding and reasoning, download the whole "
               "calendar, or select a story to take it into press-release generation.")

    # ---- download the whole calendar without proceeding ----
    brand = (st.session_state.get("client") or {}).get("name", "")
    dl1, dl2, _ = st.columns([1.1, 1, 3])
    try:
        cal_md = prcalendar.calendar_markdown(cal)
        dl1.download_button(" Calendar (Markdown)", cal_md.encode("utf-8"),
                            file_name="pr-calendar.md", mime="text/markdown", key="prcal_dl_md")
        dl2.download_button(" Calendar (PDF)",
                            docs.markdown_to_pdf(cal_md, brand=brand, topic="12-Month Press-Release Calendar",
                                                 article_type="PR Calendar", language="English"),
                            file_name="pr-calendar.pdf", mime="application/pdf", key="prcal_dl_pdf")
    except Exception as e:  # noqa: BLE001
        st.caption(f"(Calendar download unavailable: {e})")

    # ---- how the PR score is calculated ----
    ex = prcalendar.scoring_explainer()
    with st.expander("How the PR score is calculated", expanded=False):
        st.markdown(f"**Formula**, `{ex['formula']}`  ·  range {ex['range']}.")
        st.markdown(ex["why_multiplicative"])
        st.markdown("**Dimensions** (each scored 1–5):")
        for _k, label, desc in ex["dimensions"]:
            st.markdown(f"- **{label}**, {desc}")
        st.markdown("**Priority bands:** "
                    + " · ".join(f"**{b}** {rng}, {note}" for b, rng, note in ex["bands"]))
        st.markdown("**Worked examples:** "
                    + " · ".join(f"`{f}` = {v} ({p})" for f, v, p in ex["worked"]))

    # ---- consulted off-graph source material (provenance) ----
    brief = st.session_state.get("pr_artifacts") or {}
    consulted = brief.get("ledger") or brief.get("documents") or []
    if consulted:
        n_read = len(brief.get("documents") or [])
        with st.expander(f" Consulted source material, {len(consulted)} off-graph artifact(s) "
                         f"({n_read} read in full · read-only)", expanded=False):
            st.caption("Prior releases / newsletters / PR reports from the Odin artifact store that this "
                       "calendar was checked against, so it doesn't re-announce existing stories and "
                       "matches the brand's voice. Each is cited by `url_key`.")
            for d in consulted:
                kind = f"`{_esc_html(d.get('kind',''))}` " if d.get("kind") else ""
                st.markdown(f"- {kind}**{_esc_html(d.get('title',''))}** "
                            f"({_esc_html(d.get('date') or 'n.d.')}) · `url_key: {_esc_html(d.get('url_key',''))}`")
    elif brief.get("collections"):
        st.caption(f" {len(brief['collections'])} artifact collection(s) found in Odin, but no individual "
                   "PR documents were readable this run, calendar built from graph grounding.")

    items = cal.get("calendar") or []
    sel_id = (st.session_state.get("selected_opp") or {}).get("id")

    def _score_bars(scores: dict) -> str:
        rows = []
        for k, label, _ in prcalendar.SCORE_DIMENSIONS:
            try:
                v = max(0, min(5, int(scores.get(k, 0))))
            except Exception:
                v = 0
            pips = "".join(f"<i class='{'on' if j < v else ''}'></i>" for j in range(5))
            rows.append(f"<div class='cs-prdim'><span class='lb'>{label}</span>"
                        f"<span class='cs-prpips'>{pips}</span></div>")
        return "".join(rows)

    def _render_story(item: dict):
        prio = item.get("priority", "Medium")
        rank = item.get("story_rank", 1)
        rk_cls = "primary" if rank == 1 else "secondary"
        rk_lbl = "Primary" if rank == 1 else "Secondary"
        pid = f"pr-{item.get('month_index', 0):02d}-{rank}"
        picked = pid == sel_id
        sc = item.get("scores") or {}
        with st.container(border=True):
            st.markdown(
                f"<span class='cs-rk {rk_cls}'>{rk_lbl}</span> "
                f"<span class='cs-imp {prio.lower()}'>{prio}</span>"
                f"<div class='cs-prti'>{' ' if picked else ''}{_esc_html(item.get('title',''))}</div>"
                f"<div class='cs-prmt'>{_esc_html(item.get('story_type',''))} · "
                f"{_esc_html(item.get('opportunity_type',''))} · {_esc_html(item.get('narrative',''))}</div>"
                f"<div class='cs-prscore'>PR score <span class='pv'>{item.get('pr_score','-')}</span></div>"
                f"{_score_bars(sc)}"
                f"<div class='cs-prwhy'><b>Why this month:</b> "
                f"{_esc_html((item.get('why_this_month') or '-'))}</div>",
                unsafe_allow_html=True)
            with st.expander("Grounding & reasoning"):
                rows = []
                if item.get("news_hook"):
                    rows.append(f"<div class='cs-prg'><b>News hook:</b> {_esc_html(item['news_hook'])}</div>")
                if item.get("brand_pov"):
                    rows.append(f"<div class='cs-prg'><b>Brand POV:</b> {_esc_html(item['brand_pov'])}</div>")
                if item.get("business_objective"):
                    rows.append(f"<div class='cs-prg'><b>Business objective:</b> {_esc_html(item['business_objective'])}</div>")
                if item.get("proof_points"):
                    pts = "; ".join(str(p) for p in item["proof_points"][:6])
                    rows.append(f"<div class='cs-prg'><b>Grounded proof points:</b> {_esc_html(pts)}</div>")
                if item.get("spokesperson"):
                    rows.append(f"<div class='cs-prg'><b>Spokesperson:</b> {_esc_html(item['spokesperson'])}</div>")
                if item.get("media_targets"):
                    mt = ", ".join(str(m) for m in item["media_targets"][:8])
                    rows.append(f"<div class='cs-prg'><b>Media targets:</b> {_esc_html(mt)}</div>")
                if item.get("audience") or item.get("market"):
                    rows.append(f"<div class='cs-prg'><b>Audience / market:</b> "
                                f"{_esc_html(item.get('audience','-'))} · {_esc_html(item.get('market','-'))}</div>")
                nodes = item.get("grounding_nodes") or []
                if nodes:
                    chips = "".join(f"<span class='node'>{_esc_html(str(n))}</span>" for n in nodes[:10])
                    rows.append(f"<div class='cs-prg'><b>Grounding (graph nodes):</b><br>{chips}</div>")
                pcov = item.get("prior_coverage") or []
                if pcov:
                    parts = []
                    for p in pcov:
                        if isinstance(p, dict) and p.get("url_key"):
                            note = f" ({_esc_html(p['note'])})" if p.get("note") else ""
                            parts.append(f"{_esc_html(p.get('relation','ref'))}  "
                                         f"<span class='node'>{_esc_html(p['url_key'])}</span>{note}")
                    if parts:
                        rows.append("<div class='cs-prg'><b>Prior coverage (off-graph provenance):</b><br>"
                                    + " ".join(parts) + "</div>")
                st.markdown("".join(rows) or "_No additional detail supplied._", unsafe_allow_html=True)
            if st.button(" Selected" if picked else "Select this story",
                         key=f"prcal_{item.get('month_index')}_{rank}",
                         type="primary" if picked else "secondary", use_container_width=True):
                if sel_id != pid:
                    for k in ("fanout", "fanout_selected", "fanout_sel_ids",
                              "brief_pool", "brief_slots"):
                        st.session_state.pop(k, None)
                # The calendar is generated lean (essentials only) for speed; generate the full
                # grounded brief for THIS story now, on demand, then take it into the release flow.
                if not prcalendar.is_enriched(item):
                    with st.spinner("Generating the full grounded story brief…"):
                        gb = st.session_state.get("grounding_bundle") or {}
                        ab = artifacts.render_pr_artifact_brief(st.session_state.get("pr_artifacts") or {})
                        enriched = prcalendar.enrich_story(
                            brand_name=brand, grounding_bundle=gb, story=item,
                            artifact_brief=ab, model="haiku")
                    item.clear(); item.update(enriched)  # persist the brief into the calendar
                st.session_state.selected_opp = prcalendar.to_opportunity(item)
                st.rerun()

    for mi in range(1, 13):
        month_items = [it for it in items if it.get("month_index") == mi]
        if not month_items:
            continue
        st.markdown(f"<div class='cs-prmonth'><span class='mn'>{mi:02d}</span>"
                    f"{_esc_html(month_items[0].get('month',''))}</div>", unsafe_allow_html=True)
        cols = st.columns(len(month_items) if len(month_items) <= 2 else 2)
        for col, item in zip(cols, month_items):
            with col:
                _render_story(item)

    opp = st.session_state.get("selected_opp")
    if opp and str(opp.get("id", "")).startswith("pr-"):
        raw = opp.get("_raw", {})
        st.divider()
        st.markdown(f"####  Selected for generation, {raw.get('month','')} · "
                    f"{'Primary' if raw.get('story_rank', 1) == 1 else 'Secondary'}")
        st.markdown(f"**{opp.get('core_topic','')}**  ·  {raw.get('story_type','')} · {raw.get('narrative','')}")
        st.caption("Continue to the next step to run the fan-out  generate  validate flow on this story, "
                   "or pick a different one above.")


def load_files_for_client():
    client = st.session_state.get("client")
    files = opportunities.list_data_files()
    files = [f for f in files if not f.name.startswith("_")]

    def _match(f):
        try:
            m, _ = opportunities.load_file(f)
            biz = (m.get("business", "") + m.get("generated_for", "")).lower()
            return client and (client["name"].split()[0].lower() in biz
                               or client["id"].replace("company-", "").split("-")[0] in biz)
        except Exception:
            return False
    default_idx = next((i for i, f in enumerate(files) if _match(f)), 0) if files else 0
    return files, default_idx


def get_grounding(scope: str, topic: str, hints: list | None = None, light: bool = False) -> dict:
    """Grounding bundle. For a non-Odin business it's a public-profile bundle (no Odin
    call, the LLM grounds from public data); otherwise live from the Odin memory graph.
    `light=True` skips the slow relation traversal (used for fast topic ideation)."""
    if is_llm():
        return prompt.public_bundle(st.session_state.get("public_profile") or {})
    return odin.gather_grounding(scope, topic, entity_hints=hints, light=light)


def gather_business_grounding(seed_topic: str, light: bool = False):
    client = st.session_state.get("client")
    if not client:
        raise RuntimeError("No business selected. Go back to the CMG Business step and choose one.")
    scope = f"{client['id']}/primary"
    return scope, get_grounding(scope, seed_topic, light=light)


# ---- topic cache (get-or-generate via the persistent disk cache; shared with prewarm) ----
def topics_cache_key(client: dict, page_snapshot: dict | None) -> str:
    return cache.key((client or {}).get("id") or (client or {}).get("name"),
                     (page_snapshot or {}).get("url") or "create",
                     st.session_state.get("article_type", "Blog Article"))


def get_topics(client: dict, page_snapshot: dict | None, *, n: int = 15, regenerate: bool = False):
    """Get-or-generate grounded topics via the persistent cache. Returns (records, generated_at).
    Pre-warmed businesses return instantly; a fresh business generates once then caches."""
    ck = topics_cache_key(client, page_snapshot)
    if not regenerate:
        data, ts = cache.load("topics", ck)
        if data:
            return opportunities.normalize(data), ts
    seed = (page_snapshot or {}).get("title") or client["name"]
    scope, bundle = gather_business_grounding(seed, light=True)
    if not is_llm():
        n_nodes = sum(len(v) for v in bundle.values() if isinstance(v, list))
        if n_nodes == 0:
            raise RuntimeError("No grounding nodes returned from Odin for this business - cannot "
                               "generate grounded topics. (Switch to a Non-Odin business for public-web "
                               "grounding.)")
    _, data = topicgen.generate_topics(
        business_id=client["id"], business_name=client["name"], scope=scope,
        grounding_bundle=bundle, page_snapshot=page_snapshot, n=n, model="haiku",
        article_type=st.session_state.get("article_type", "Blog Article"), use_cache=False)
    ts = cache.save("topics", ck, data)
    return opportunities.normalize(data), ts


def _load_cached_topics(client: dict, page_snapshot: dict | None):
    """Sync session topic records with the cache for the current business+page; returns
    (records, generated_at). Invalidates session records when the business/page changes."""
    ck = topics_cache_key(client, page_snapshot)
    if st.session_state.get("gen_records_key") != ck:
        st.session_state.gen_records = None
        st.session_state.gen_records_ts = None
        st.session_state.gen_records_key = ck
    if st.session_state.get("gen_records") is None:
        data, ts = cache.load("topics", ck)
        if data:
            st.session_state.gen_records = opportunities.normalize(data)
            st.session_state.gen_records_ts = ts
    return st.session_state.get("gen_records"), st.session_state.get("gen_records_ts")


# ---- content cache (replay an identical generation configuration instantly) ----
_CONTENT_KEYS = ("generated_md", "content_blocks", "block_records", "validation_md",
                 "enhancements", "overall_block_score", "factcheck")
# validation-derived keys — generated on demand in Review, NOT during the fast draft
_VAL_KEYS = ("block_records", "validation_md", "enhancements", "overall_block_score", "factcheck")


def content_cache_key(opp: dict, client: dict, mode: str) -> str:
    """Stable key over every input that affects the generated draft."""
    s = st.session_state
    return cache.key(
        (client or {}).get("id"), (opp or {}).get("id"), mode, eff_type(),
        s.get("output_language", "English"), s.get("model", "opus"),
        s.get("brand_voice_text", ""), s.get("target_audience", ""), s.get("cta", ""),
        s.get("topic_qa", ""), ",".join(sorted(s.get("fanout_sel_ids") or [])),
        s.get("page_url", "") if mode == "optimize" else "",
        s.get("opt_plan", "") if mode == "optimize" else "",
        ",".join(sorted(str(e) for e in (s.get("applied_enhancements") or []))))


# ---- real internal links (from the client's sitemap) — finding 9 ----
def _site_url_for(client: dict | None, bundle: dict | None) -> str:
    """Best-effort base URL for the client: optimize page → grounding website → public profile."""
    if st.session_state.get("mode") == "optimize" and st.session_state.get("page_url"):
        return st.session_state["page_url"]
    pp = st.session_state.get("public_profile") or {}
    if pp.get("url"):
        return pp["url"]
    for rows in (bundle or {}).values():
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            for k, v in (r.get("facts") or {}).items():
                if isinstance(v, str) and re.match(r"^https?://", v) and "website" in k.lower():
                    return v
            if isinstance(r.get("url"), str) and r["url"].startswith("http"):
                return r["url"]
    return ""


def get_internal_links(client: dict | None, bundle: dict | None) -> list[dict]:
    """Get-or-cache the client's real sitemap URLs. Returns [] if none discoverable."""
    site = _site_url_for(client, bundle)
    if not site:
        return []
    ck = cache.key("sitemap", site)
    data, _ = cache.load("sitemap", ck)
    if data is not None:
        return data
    from lib import sitemap
    links = sitemap.fetch_internal_links(site)
    cache.save("sitemap", ck, links)
    return links


# ---- content cannibalization ledger — finding 10 ----
def _pieces_key(client: dict | None) -> str:
    return cache.key("pieces", (client or {}).get("id") or (client or {}).get("name") or "biz")


def _token_set(*strs) -> set:
    words = re.findall(r"[a-z0-9]+", " ".join(s for s in strs if s).lower())
    stop = {"the", "and", "for", "with", "your", "our", "a", "an", "of", "to", "in", "on",
            "best", "guide", "how", "what", "vs", "at", "is", "are", "you"}
    return {w for w in words if len(w) > 2 and w not in stop}


def check_cannibalization(client: dict | None, opp: dict) -> list[dict]:
    """Warn if this topic strongly overlaps a piece already generated for this client."""
    ledger, _ = cache.load("pieces", _pieces_key(client))
    ledger = ledger or []
    cur = _token_set(opp.get("core_topic"), " ".join(opp.get("keywords") or []))
    if not cur:
        return []
    hits = []
    for p in ledger:
        prev = set(p.get("tokens") or [])
        if not prev:
            continue
        jac = len(cur & prev) / max(1, len(cur | prev))
        if jac >= 0.5 and p.get("topic", "").lower() != (opp.get("core_topic") or "").lower():
            hits.append({"topic": p.get("topic"), "format": p.get("format"),
                         "overlap": round(jac * 100), "at": p.get("at")})
    return sorted(hits, key=lambda h: -h["overlap"])[:4]


def record_piece(client: dict | None, opp: dict, article_type: str):
    """Append this generated piece to the client's ledger (for cannibalization checks)."""
    k = _pieces_key(client)
    ledger, _ = cache.load("pieces", k)
    ledger = ledger or []
    slug = docs.safe_slug(opp.get("core_topic") or "content")
    ledger = [p for p in ledger if p.get("slug") != slug][:200]  # replace same slug
    import datetime as _dt
    ledger.append({"slug": slug, "topic": opp.get("core_topic"), "format": article_type,
                   "tokens": sorted(_token_set(opp.get("core_topic"),
                                               " ".join(opp.get("keywords") or []))),
                   "at": _dt.datetime.now().isoformat(timespec="seconds")})
    cache.save("pieces", k, ledger)


def get_pr_artifact_brief(scope: str) -> dict:
    """Read-only off-graph artifact brief (prior releases / newsletters / PR reports),
    cached per run. Empty for a non-Odin business (no artifact store) and on any failure,
    so PR generation always falls back to the graph grounding. Re-raises OdinAuthError."""
    if is_llm():
        return {"available": False, "documents": [], "collections": [], "error": "non-Odin"}
    b = st.session_state.get("pr_artifacts")
    if b is None:
        try:
            b = artifacts.gather_pr_artifacts(scope)
        except odin.OdinAuthError:
            raise
        except Exception as e:  # noqa: BLE001
            b = {"available": False, "documents": [], "collections": [], "error": str(e)}
        st.session_state.pr_artifacts = b
    return b


# ================================================================== chrome
steps = order()
step = st.session_state.step
key = steps[step]
ui.header(header_chips())
ui.step_rail(steps, LABELS, step)
with st.sidebar:
    # Compact status line — a single green/amber dot + one-word state, no boxes.
    eng = st.session_state.get("engine_health")
    if eng is None:
        eng = generate.health()
        st.session_state.engine_health = eng
    if is_llm():
        grounding_state = ("#5B5BD6", "Public web")
    else:
        conn = st.session_state.get("odin_conn")
        if conn is None:
            grounding_state = ("#6B7280", "Odin: at Business step")
        elif conn.get("ok"):
            grounding_state = ("#0E9F6E", f"Odin: {conn.get('signed_in_as') or 'connected'}")
        elif conn.get("needs_reauth"):
            grounding_state = ("#C0392B", "Odin: sign-in needed")
        else:
            grounding_state = ("#C0392B", "Odin: not connected")
    eng_dot = "#0E9F6E" if eng.get("ok") else "#C0392B"
    eng_name = "API" if eng.get("backend") == "api" else "Claude CLI"
    st.markdown(
        f"<div class='cs-railstat'>"
        f"<span><i style='background:{grounding_state[0]}'></i>{grounding_state[1]}</span>"
        f"<span><i style='background:{eng_dot}'></i>Engine: {eng_name}</span></div>",
        unsafe_allow_html=True)

    with st.popover("System & settings", use_container_width=True):
        _MODEL_LABELS = {"opus": "Opus 4.8", "sonnet": "Sonnet 4.6"}
        st.session_state.model = st.selectbox(
            "Generation model", ["opus", "sonnet"], index=0,
            format_func=lambda m: _MODEL_LABELS.get(m, m))
        st.divider()
        if is_llm():
            st.caption("**Public web (LLM) grounding** — this business is not in Odin; topics, "
                       "research, and content are grounded from public sources and cited.")
        else:
            conn = st.session_state.get("odin_conn") or {}
            st.caption(f"**Odin:** {grounding_state[1].replace('Odin: ', '')}")
            if conn.get("message"):
                st.caption(conn["message"])
            if st.button("Recheck Odin", use_container_width=True):
                odin.list_clients.cache_clear()
                with st.spinner("Rechecking Odin…"):
                    st.session_state.odin_conn = odin.probe()
                st.rerun()
        st.divider()
        st.caption(f"**Engine ({eng_name}):** {eng.get('detail', '')}")
        if st.button("Recheck engine", use_container_width=True):
            st.session_state.engine_health = generate.health()
            st.rerun()
        _runs = runlog.summary()
        if _runs.get("total"):
            st.divider()
            st.caption(
                f"**Run log** · {_runs['total']} generations · avg {_runs.get('avg_duration_s', 0)}s "
                f"· cache {round(_runs.get('cache_hit_rate', 0) * 100)}% · gate-fail "
                f"{round(_runs.get('gate_fail_rate', 0) * 100)}%")

# step 1 owns its hero headline, so we skip the duplicate step title there
ui.step_heading(LABELS[key], step, len(steps), show_title=(key != "objective"))

main, side = st.columns([2.35, 1], gap="large")
with side:
    ui.reasoning_card(reasoning.reason(key, st.session_state))

with main:
    # -------------------------------------------------- objective
    if key == "objective":
        st.markdown(
            "<div class='cs-hero'><div class='h'>Content the machines cite, and people trust.</div>"
            "<div class='s'>Turn a business's knowledge into publish-ready content that AI answer engines "
            "quote, with every claim traced to its source and scored on KAIROS. Choose how you want to "
            "begin.</div></div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2, gap="large")
        with c1:
            with st.container(border=False):
                st.markdown(
                    "<div class='cs-opt'>"
                    "<div class='iconbadge'><svg viewBox='0 0 24 24' fill='none' width='22' height='22'>"
                    "<path d='M12 3v4M12 3l-2.2 1.3M12 3l2.2 1.3M5 8.5l3.5 2M19 8.5l-3.5 2M12 21a6 6 0 0 0 "
                    "6-6c0-2.5-1.8-4.2-3-5.5-1-1.1-1.4-2-1.4-2h-3.2s-.4.9-1.4 2C9.8 10.8 8 12.5 8 15a6 6 0 0 0 4 6Z' "
                    "stroke='currentColor' stroke-width='1.6' stroke-linejoin='round'/></svg></div>"
                    "<div class='ti'>Create New Content</div>"
                    "<div class='de'>Start from a grounded opportunity and generate a publish-ready, "
                    "citable page: researched, written, and KAIROS-scored end to end.</div></div>",
                    unsafe_allow_html=True)
                if st.button("Start Creating", use_container_width=True, type="primary",
                             key="obj_create"):
                    st.session_state.mode = "create"; goto(1); st.rerun()
        with c2:
            with st.container(border=False):
                st.markdown(
                    "<div class='cs-opt'>"
                    "<div class='iconbadge'><svg viewBox='0 0 24 24' fill='none' width='22' height='22'>"
                    "<path d='M20 12a8 8 0 1 1-2.3-5.6M20 4v3.5h-3.5' stroke='currentColor' stroke-width='1.6' "
                    "stroke-linecap='round' stroke-linejoin='round'/><circle cx='12' cy='12' r='2.6' "
                    "stroke='currentColor' stroke-width='1.6'/></svg></div>"
                    "<div class='ti'>Optimize An Existing Page</div>"
                    "<div class='de'>Paste a URL. We crawl the real copy, audit it against AI-search "
                    "demand, and rewrite it to win citations without losing what works.</div></div>",
                    unsafe_allow_html=True)
                if st.button("Optimize A Page", use_container_width=True, type="primary",
                             key="obj_optimize"):
                    st.session_state.mode = "optimize"; goto(1); st.rerun()

    # -------------------------------------------------- output (format + language)
    elif key == "output":
        st.write("Choose the output **format** and **language** up front, this shapes structure, "
                 "schema, and how the whole pipeline builds the answer.")
        st.session_state.article_type = st.selectbox(
            "Output format", FORMATS, key="out_format",
            index=FORMATS.index(st.session_state.get("article_type", "Blog Article")))
        st.session_state.output_language = st.selectbox(
            "Output language", LANGUAGES, key="out_language",
            index=LANGUAGES.index(st.session_state.get("output_language", "English")))
        nav()

    # -------------------------------------------------- business
    elif key == "business":
        ui.lede("Choose how to power this workflow. An **Odin business** is grounded in the memory "
                "graph. A **Non-Odin business** is grounded entirely from the **public web via the "
                "LLM**, for any business that isn't ingested into Odin.")
        # Square tile chooser (border-radius 5px) instead of a plain radio
        cur_llm = is_llm()
        t1, t2 = st.columns(2)
        for col, is_non, title, desc, key_ in [
            (t1, False, "Odin Business", "Grounded from the Odin memory graph.", "src_odin"),
            (t2, True, "Non-Odin Business", "Grounded from the public web via the LLM.", "src_llm")]:
            sel = (cur_llm == is_non)
            col.markdown(
                f"<div class='cs-srctile {'on' if sel else ''}'><div class='ti'>{title}</div>"
                f"<div class='de'>{desc}</div></div>", unsafe_allow_html=True)
            if col.button(("Selected" if sel else "Select"), key=key_, use_container_width=True,
                          type="primary" if sel else "secondary"):
                st.session_state.grounding_source = "llm" if is_non else "odin"
                st.rerun()
        non_odin = is_llm()

        if non_odin:
            pp = st.session_state.get("public_profile") or {}
            st.caption("No Odin data will be used. Provide the business identity below, every topic, "
                       "competitive analysis, recommendation, and the content itself will be generated "
                       "from public-domain information and cited to real sources.")
            name = st.text_input("Business name", value=pp.get("name", ""),
                                 placeholder="e.g. The Beach House Goa")
            ptype = st.radio("The profile is a…", ["Location", "Brand"], horizontal=True,
                             index=0 if pp.get("profile_type", "Location") == "Location" else 1,
                             key="np_ptype")
            pname = st.text_input(f"{ptype} name", value=pp.get("profile_name", ""),
                                  placeholder=("e.g. Goa, India" if ptype == "Location"
                                               else "e.g. The Beach House Collection"))
            url = st.text_input("Website URL", value=pp.get("url", ""),
                                placeholder="https://www.example.com")
            ready = bool(name.strip() and pname.strip() and url.strip())
            if ready:
                profile = {"name": name.strip(), "profile_type": ptype,
                           "profile_name": pname.strip(), "url": url.strip()}
                st.session_state.public_profile = profile
                slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "business"
                st.session_state.client = {"id": f"nonodin-{slug}", "name": name.strip(),
                                           "non_odin": True, "url": url.strip(),
                                           "profile_name": pname.strip(), "profile_type": ptype}
                st.session_state.odin_conn = {"ok": False, "needs_reauth": False,
                                              "message": "non-Odin (public web)"}
                st.success(f" Public-web grounding set for **{name.strip()}**, "
                           f"{ptype}: {pname.strip()}. Everything downstream is LLM-powered.")
            else:
                st.info("Enter the business name, profile name, and website URL to continue.")
            nav(next_disabled=not ready)
            st.stop()

        # ---- Odin business ----
        st.session_state.pop("public_profile", None)
        st.write("Which business profile should we ground against? (live from Odin)")
        clients: list[dict] = []
        # This is the one place we verify Odin live (behind a spinner) and cache the result,
        # so no other step, including step 1, ever blocks on an Odin call.
        with st.spinner("Connecting to Odin…"):
            try:
                clients = odin.list_clients()
                st.session_state.odin_conn = {
                    "ok": True, "needs_reauth": False, "message": "connected",
                    "signed_in_as": odin.auth_status().get("signed_in_as", "")}
            except odin.OdinAuthError as e:
                st.session_state.odin_conn = {"ok": False, "needs_reauth": True, "message": str(e)}
                st.error(" " + str(e) + "  Then reload this step (or click ** Recheck Odin**). "
                         "No Odin access? Switch to **Non-Odin business** above.")
            except Exception as e:  # noqa: BLE001
                st.session_state.odin_conn = {"ok": False, "needs_reauth": False, "message": str(e)}
                st.error(f" Could not reach Odin: {e}\n\nIf you just signed in with `odin auth login`, "
                         "click ** Recheck Odin** in the sidebar, or switch to **Non-Odin business** above.")
        if clients:
            labels = [f"{c['name']}  ·  {c['id']}" for c in clients]
            di = next((i for i, c in enumerate(clients) if "grand-velas" in c["id"]), 0)
            pick = st.selectbox("Business", range(len(clients)), key="business_pick",
                                format_func=lambda i: labels[i], index=di)
            st.session_state.client = clients[pick]
            st.info(f"Grounding scope  `{clients[pick]['id']}/primary`")
        nav(next_disabled=not clients)

    # -------------------------------------------------- url (optimize)
    elif key == "url":
        st.write("Paste the URL of the page you want to optimize.")
        url = st.text_input("Page URL", value=st.session_state.get("page_url", ""),
                            placeholder="https://vallarta.grandvelas.com/weddings")
        st.session_state.page_url = url
        if url and st.button("  Crawl & extract main content", type="primary"):
            with st.spinner("Rendering (headless browser) and extracting the real page copy…"):
                try:
                    st.session_state.crawl = crawl.crawl(url)
                    st.session_state.pop("gen_records", None)  # invalidate downstream
                except Exception as e:  # noqa: BLE001
                    st.error(f"Crawl failed: {e}")
        snap = st.session_state.get("crawl")
        if snap:
            st.success(f"Extracted **{snap['word_count']} words** of page copy via "
                       f"`{snap['fetch_method']}`  ·  schema: {', '.join(snap['schema_types']) or 'none'}")
            st.write(f"**Title:** {snap['title']}")
            with st.expander("Extracted main content (chrome removed)"):
                st.write("**H2s:** " + " · ".join(snap["headings"]["h2"][:15]))
                st.text(snap["body_text"][:2500])
        nav(next_disabled=not snap)

    # -------------------------------------------------- gentopics (optimize)
    elif key == "gentopics":
        snap = st.session_state.get("crawl")
        client = st.session_state.get("client")
        if not client:
            st.warning("Select a business first. Go back to the **CMG Business** step and choose (or "
                       "set up) a business, then return here.")
            nav(next_disabled=True)
            st.stop()
        llm = is_llm()
        src_txt = ("public-web knowledge (this business is not in Odin)" if llm
                   else "the Odin **Context Memory Graph (CMG)**")
        ui.lede(f"We read this page's full content, pull context from {src_txt}, and generate "
                "grounded opportunities that extend this page, fill its gaps, and capture adjacent "
                "AI-search demand.")
        # Odin connectivity check up front (live probe, not just the stored token)
        conn = st.session_state.get("odin_conn") or {}
        if llm:
            st.caption("Public-web grounding, topics generated from public sources and cited.")
        elif conn.get("ok"):
            st.caption(f"Odin connected as {conn.get('signed_in_as','?')}, grounding from the CMG.")
        else:
            st.error((conn.get("message") or "Odin is not connected, so topics can't be grounded.")
                     + "  Use **Recheck Odin** in the sidebar after signing in.")
        recs, ts = _load_cached_topics(client, snap)
        can_gen = llm or conn.get("ok")
        action = ui.gen_status_bar(
            has_data=bool(recs), generated_at=ts, key="gentopics",
            generate_label="Generate grounded topics",
            busy_hint="~1 minute · grounded in this page + business")
        if action:
            if not can_gen:
                st.error(conn.get("message") or "Odin is not connected. Use **Recheck Odin** first.")
            else:
                with st.status("Generating grounded opportunities…", expanded=True) as status:
                    try:
                        recs, ts = get_topics(client, snap, n=15, regenerate=(action == "regenerate"))
                        st.session_state.gen_records = recs
                        st.session_state.gen_records_ts = ts
                        status.update(label=f"Generated {len(recs)} topics", state="complete")
                        st.rerun()
                    except odin.OdinAuthError as e:
                        st.session_state.odin_conn = {"ok": False, "needs_reauth": True, "message": str(e)}
                        status.update(label="Odin sign-in needed", state="error"); st.error(str(e))
                    except Exception as e:  # noqa: BLE001
                        status.update(label="Generation failed", state="error")
                        st.error(f"Couldn't generate topics: {e}")
        if recs:
            st.dataframe(
                [{"topic": r["core_topic"], "pillar": r["pillar_topic"], "intent": r["intent"],
                  "GEO lift": r["geo_lift"], "gap": r["content_gap_type"]} for r in recs],
                use_container_width=True, height=280)
        nav(next_disabled=not recs)

    # -------------------------------------------------- match (optimize)
    elif key == "match":
        recs = st.session_state.get("gen_records") or []
        snap = st.session_state.get("crawl")
        if not recs:
            st.warning("Generate topics first (previous step).")
        else:
            terms = crawl.page_terms(snap, include_body=True)
            ranked = matcher.match(recs, terms, top_k=len(recs))
            st.write("Topics scored against **this page's actual content**, grouped by category. "
                     "Expand a group and select one to optimize toward:")
            render_topic_picker(ranked, "match", show_match=True)
        nav(next_disabled=not st.session_state.get("selected_opp"))

    # -------------------------------------------------- plan (optimize)
    elif key == "plan":
        opp = st.session_state.get("selected_opp")
        snap = st.session_state.get("crawl")
        client = st.session_state.get("client")
        if not (opp and snap and client):
            st.warning("Need a crawled page and a selected topic first. Go back.")
        else:
            st.write("Before generating, the system analyses the existing page against your target "
                     "topic, the Odin graph, and the live competitor landscape, and tells you exactly "
                     "what it will **Retain, Enhance, Prune, and Create**.")
            ck = cache.key(client["id"], opp.get("id"), (snap or {}).get("url") or "")
            if st.session_state.get("opt_plan_key") != ck:
                st.session_state.opt_plan = None
                st.session_state.opt_plan_ts = None
                st.session_state.opt_plan_key = ck
            plan, ts = st.session_state.get("opt_plan"), st.session_state.get("opt_plan_ts")
            if plan is None:
                data, ts = cache.load("optplan", ck)
                if data:
                    st.session_state.opt_plan = plan = data
                    st.session_state.opt_plan_ts = ts
            action = ui.gen_status_bar(
                has_data=bool(plan), generated_at=ts, key="optplan",
                generate_label="Analyse & build optimization plan",
                regenerate_label="Re-run", busy_hint="2–3 minutes · page vs Odin + competitors")
            if action:
                with st.status("Analysing page vs. target topic, Odin, and competitors…",
                               expanded=True) as status:
                    try:
                        scope = f"{client['id']}/primary"
                        bundle = st.session_state.get("grounding_bundle") or get_grounding(
                            scope, opp["core_topic"], hints=opp.get("entities"))
                        st.session_state.grounding_bundle = bundle
                        st.write("Building the Retain / Enhance / Prune / Create plan…")
                        st.session_state.opt_plan = optplan.run_plan(
                            brand_name=client["name"],
                            article_type=st.session_state.get("article_type", "Web Page"),
                            opportunity=opp, crawl_snapshot=snap, grounding_bundle=bundle,
                            model=fast_model())
                        st.session_state.opt_plan_ts = cache.save("optplan", ck, st.session_state.opt_plan)
                        status.update(label="Optimization plan ready", state="complete")
                        st.rerun()
                    except odin.OdinAuthError as e:
                        st.session_state.odin_conn = {"ok": False, "needs_reauth": True, "message": str(e)}
                        status.update(label="Odin sign-in needed", state="error"); st.error(str(e))
                    except Exception as e:  # noqa: BLE001
                        status.update(label="Analysis failed", state="error")
                        st.error(f"Analysis error: {e}")
            plan = st.session_state.get("opt_plan")
            if plan:
                st.caption("This is what the generator will do to the page. Review, then continue.")
                for tag, cls, label in [("RETAIN", "retain", "● Retain, keep what works"),
                                        ("ENHANCE", "enhance", "● Enhance, strengthen what's weak"),
                                        ("PRUNE", "prune", "● Prune, cut what suppresses citation"),
                                        ("CREATE", "create", "● Create, add what's missing")]:
                    body = docs.extract_fence(plan, tag) or "_(nothing in this bucket)_"
                    st.markdown(
                        f'<div class="cs-bucket {cls}"><div class="bh">{label}</div>'
                        f'<div class="bb">{markdown2.markdown(body)}</div></div>',
                        unsafe_allow_html=True)
                summ = docs.extract_fence(plan, "PLAN_SUMMARY")
                if summ:
                    st.markdown(f"**Plan summary**, {summ}")
        nav(next_disabled=not st.session_state.get("opt_plan"))

    # -------------------------------------------------- topic (create)
    elif key == "topic":
        client = st.session_state.get("client")
        if not client:
            st.warning("Select a business first. Go back to the **CMG Business** step and choose (or "
                       "set up) a business, then return here.")
            nav(next_disabled=True)
            st.stop()
        files, di = load_files_for_client()
        if is_llm():
            st.write("This business isn't in Odin, **generate a fresh set of topics** from public-web "
                     "knowledge below (there's no pre-built opportunity library for it).")
        else:
            st.write("Select an Odin-grounded opportunity, or generate a fresh set now.")
        records, ts = _load_cached_topics(client, None)
        action = ui.gen_status_bar(
            has_data=bool(records), generated_at=ts, key="topic",
            generate_label=("Generate topics from public web" if is_llm()
                            else "Generate grounded topics"),
            busy_hint="~1 minute · grounded in this business")
        if action:
            with st.status("Generating grounded opportunities…", expanded=True) as status:
                try:
                    records, ts = get_topics(client, None, n=15, regenerate=(action == "regenerate"))
                    st.session_state.gen_records = records
                    st.session_state.gen_records_ts = ts
                    status.update(label=f"Generated {len(records)} topics", state="complete")
                    st.rerun()
                except odin.OdinAuthError as e:
                    st.session_state.odin_conn = {"ok": False, "needs_reauth": True, "message": str(e)}
                    status.update(label="Odin sign-in needed", state="error"); st.error(str(e))
                except Exception as e:  # noqa: BLE001
                    status.update(label="Generation failed", state="error"); st.error(str(e))
        if not records and files:
            with st.expander("Or pick from the pre-built opportunity library"):
                fpick = st.selectbox("Opportunity library", range(len(files)),
                                     format_func=lambda i: files[i].name, index=di)
                _, records = opportunities.load_file(files[fpick])
        if records:
            render_topic_picker(records, "create")
        nav(next_disabled=not st.session_state.get("selected_opp"))

    # -------------------------------------------------- prcalendar (PR Calendar format)
    elif key == "prcalendar":
        client = st.session_state.get("client")
        if not client:
            st.warning("Select a business first (Business step).")
        else:
            llm = is_llm()
            _src = ("public-web knowledge of this business" if llm
                    else "this business's Odin data, historical PR performance, competitor activity, "
                         "guest interests, and business objectives")
            st.write(f"KAIROS builds a **12-month press-release calendar** grounded in {_src}. It "
                     "establishes the strategic narratives, scores every opportunity (Newsworthiness × "
                     "Brand fit × Audience × Media × Timing), and places **one contextual, newsworthy "
                     "story in each month**.")
            conn = st.session_state.get("odin_conn") or {}
            if llm:
                st.caption(" Public-web grounding, the calendar is built from public sources and cited.")
            elif conn.get("ok"):
                st.caption(f" Odin connected as {conn.get('signed_in_as','?')}, grounded in the CMG.")
            else:
                st.error(" " + (conn.get("message") or "Odin is not connected.")
                         + "  Use ** Recheck Odin** in the sidebar.")
            import datetime
            year = datetime.date.today().year + 1
            ck = cache.key(client["id"], f"pr-{year}")
            if st.session_state.get("pr_calendar_key") != ck:
                st.session_state.pr_calendar = None
                st.session_state.pr_calendar_ts = None
                st.session_state.pr_calendar_key = ck
            cal, ts = st.session_state.get("pr_calendar"), st.session_state.get("pr_calendar_ts")
            if cal is None:
                data, ts = cache.load("prcalendar", ck)
                if data:
                    st.session_state.pr_calendar = cal = data
                    st.session_state.pr_calendar_ts = ts
            action = ui.gen_status_bar(
                has_data=bool(cal), generated_at=ts, key="prcal",
                generate_label="Generate 12-month PR calendar",
                busy_hint="~2–3 minutes · 24 grounded, scored stories")
            if action:
                if not (llm or conn.get("ok")):
                    st.error(conn.get("message") or "Odin is not connected. Use **Recheck Odin** first.")
                else:
                    with st.status("Building the grounded PR calendar…", expanded=True) as status:
                        try:
                            st.write("① Using public-web knowledge for PR context…" if llm
                                     else "① Pulling PR-relevant context from the Odin CMG…")
                            scope = f"{client['id']}/primary"
                            seed = (f"{client['name']} press release PR media coverage awards announcements "
                                    "seasonal competitor guest interests business objectives")
                            bundle = st.session_state.get("grounding_bundle") or get_grounding(scope, seed, light=True)
                            st.session_state.grounding_bundle = bundle
                            art_brief = {"available": False, "documents": [], "ledger": []}
                            brief_text = ""
                            if not llm:
                                st.write("② Consulting prior PR artifacts (releases, newsletters, reports)…")
                                art_brief = get_pr_artifact_brief(scope)
                                n_led = len(art_brief.get("ledger") or [])
                                n_doc = len(art_brief.get("documents") or [])
                                st.write(f"   {n_led} prior artifact(s) consulted · {n_doc} read in full."
                                         if n_led else "   No off-graph PR artifacts found, using graph grounding.")
                                brief_text = artifacts.render_pr_artifact_brief(art_brief)
                            data = ui.run_with_progress(
                                lambda: prcalendar.generate_calendar(
                                    brand_name=client["name"], grounding_bundle=bundle, year=year,
                                    model="haiku", artifact_brief=brief_text),
                                expected_seconds=150,
                                label="③ Narratives, scoring, scheduling (4 quarters in parallel)")
                            data["_consulted"] = art_brief.get("ledger") or art_brief.get("documents") or []
                            st.session_state.pr_calendar = data
                            st.session_state.pr_calendar_ts = cache.save("prcalendar", ck, data)
                            status.update(label=f"Built a {len(data['calendar'])}-month calendar",
                                          state="complete")
                            st.rerun()
                        except odin.OdinAuthError as e:
                            st.session_state.odin_conn = {"ok": False, "needs_reauth": True, "message": str(e)}
                            status.update(label="Odin sign-in needed", state="error"); st.error(str(e))
                        except Exception as e:  # noqa: BLE001
                            status.update(label="Calendar generation failed", state="error"); st.error(str(e))
            cal = st.session_state.get("pr_calendar")
            if cal:
                st.divider()
                render_pr_calendar(cal)
        nav(next_disabled=not str((st.session_state.get("selected_opp") or {}).get("id", "")).startswith("pr-"))

    # -------------------------------------------------- fanout (both modes)
    elif key == "fanout":
        opp = st.session_state.get("selected_opp")
        client = st.session_state.get("client")
        mode = st.session_state.get("mode", "create")
        snap = st.session_state.get("crawl") if mode == "optimize" else None
        if not opp or not client:
            st.warning("Select a topic first (previous step).")
        else:
            ui.lede("AI search answers a question by **fanning it out** into many sub-queries. We derive "
                    "**5 original queries** from your topic and fan each into the decision criteria an "
                    "engine would explore - every one classified with a **Qforia type**, **user intent**, "
                    "and **reasoning**. "
                    + ("Each query is also judged **covered / partial / missing** against the page."
                       if snap else "Curate the set; your ticked rows become the generation targets."))
            with st.expander("Fan-out options"):
                c1, c2 = st.columns(2)
                depth_label = c1.selectbox("Depth", list(fanout.DEPTHS), index=0,
                                           help="Standard = supporting questions; Deep adds decision "
                                                "& prerequisite questions.")
                limit = c2.slider("Target query count", 12, 30, st.session_state.get("fanout_limit", 16))
                st.session_state.fanout_limit = limit

            # cache sync (per business + topic + page)
            fk = cache.key(client["id"], opp.get("id"), (snap or {}).get("url") or "")
            if st.session_state.get("fanout_key") != fk:
                st.session_state.fanout = None
                st.session_state.fanout_ts = None
                st.session_state.fanout_key = fk
            fo, ts = st.session_state.get("fanout"), st.session_state.get("fanout_ts")
            if fo is None:
                data, ts = cache.load("fanout", fk)
                if data:
                    st.session_state.fanout = fo = data
                    st.session_state.fanout_ts = ts
                    _seed_fanout_selection(data)

            action = ui.gen_status_bar(
                has_data=bool(fo), generated_at=ts, key="fanout",
                generate_label="Generate query fan-out",
                busy_hint="~1 minute · grounded in this business")
            if action:
                with st.status("Mapping the AI-search query space…", expanded=True) as status:
                    try:
                        st.write("① Pulling grounding from the Odin Context Memory Graph…")
                        scope = f"{client['id']}/primary"
                        bundle = (st.session_state.get("grounding_bundle")
                                  or get_grounding(scope, opp["core_topic"], hints=opp.get("entities")))
                        st.session_state.grounding_bundle = bundle
                        data = ui.run_with_progress(
                            lambda: fanout.run_fanout(
                                opp=opp, brand_name=client["name"],
                                target_audience=st.session_state.get("target_audience", ""),
                                output_language=st.session_state.get("output_language", "English"),
                                grounding_bundle=bundle, page_snapshot=snap,
                                depth=fanout.DEPTHS[depth_label], fanout_limit=limit, model="haiku"),
                            expected_seconds=75,
                            label="② Deriving 5 originals, fanning out + Qforia classification"
                                  + (" + judging page coverage" if snap else ""))
                        st.session_state.fanout = data
                        st.session_state.fanout_ts = cache.save("fanout", fk, data)
                        st.session_state.pop("brief_pool", None)  # Q&A must re-derive from new fan-out
                        st.session_state.pop("brief_slots", None)
                        _seed_fanout_selection(data)
                        status.update(label=f"Mapped {len(data['queries'])} queries", state="complete")
                        st.rerun()
                    except odin.OdinAuthError as e:
                        st.session_state.odin_conn = {"ok": False, "needs_reauth": True, "message": str(e)}
                        status.update(label="Odin sign-in needed", state="error"); st.error(str(e))
                    except Exception as e:  # noqa: BLE001
                        status.update(label="Fan-out failed", state="error"); st.error(str(e))
            fo = st.session_state.get("fanout")
            if fo:
                st.divider()
                render_fanout(fo, snap is not None)
                collect_fanout_selection(fo)
        nav(next_disabled=not st.session_state.get("fanout"))

    # -------------------------------------------------- preferences (brand voice + audience)
    elif key == "preferences":
        render_preferences()
        nav()

    # -------------------------------------------------- qa
    elif key == "qa":
        opp = st.session_state.get("selected_opp")
        if not opp:
            back_to = "Generate Topics / Match Topic" if st.session_state.get("mode") == "optimize" \
                else "Choose Topic"
            st.info(f"**No topic selected yet.** These optional questions are drawn from the topic you "
                    f"pick. Please go back to the **{back_to}** step, create/select a topic, then return "
                    f"here. You can also skip this step, it's optional.")
        else:
            fo_sel = st.session_state.get("fanout_selected") or []
            # Bucket-① backfill: lead with criteria whose honest answer lives in first-party /
            # unpublished data (white space + "first-party needed"), these are exactly the facts
            # to elicit from the author that competitors structurally can't surface.
            fo_sel = sorted(
                fo_sel,
                key=lambda q: (q.get("answerable_from") != "First-party needed",
                               q.get("whitespace") != "White space",
                               -int(q.get("priority", q.get("importance", 0) or 0))))
            brand = (st.session_state.get("client") or {}).get("name", "")
            if fo_sel:
                st.write("These questions are drawn from your approved fan-out and grounded to this "
                         "topic, answer any with **first-party detail** (real numbers, named venues, "
                         "policies) to make the content original. Use  to swap a question you don't want.")
                pool = st.session_state.get("brief_pool")
                if pool is None:
                    qkey = cache.key((st.session_state.get("client") or {}).get("id"), opp.get("id"),
                                     ",".join(sorted(q.get("id", "") for q in fo_sel)))
                    pool, _ = cache.load("briefqa", qkey)
                    if pool is None:
                        with st.spinner("Preparing grounded questions from your fan-out…"):
                            try:
                                pool = briefqa.run(
                                    brand_name=brand, seed_topic=opp.get("core_topic", ""),
                                    fanout_queries=fo_sel,
                                    grounding_bundle=st.session_state.get("grounding_bundle") or {},
                                    n=8, model=fast_model())
                                cache.save("briefqa", qkey, pool)
                            except Exception as e:  # noqa: BLE001
                                pool = [q.get("query") for q in fo_sel][:8]
                                st.caption(f"(Falling back to fan-out queries, {e})")
                    st.session_state.brief_pool = pool
                    st.session_state.brief_slots = list(range(min(3, len(pool))))
                pool = st.session_state.brief_pool
                slots = st.session_state.get("brief_slots") or list(range(min(3, len(pool))))
                pairs = []
                for si, pidx in enumerate(slots):
                    q = pool[pidx]
                    head, ref = st.columns([11, 1])
                    head.markdown(f"**Q{si+1}.** {q}")
                    if ref.button("", key=f"qa_ref_{si}", help="Swap this question for another"):
                        used = set(slots)
                        nxt = next((j for j in range(len(pool)) if j not in used), None)
                        if nxt is None:  # pool exhausted, fetch more grounded questions
                            try:
                                with st.spinner("Fetching more questions…"):
                                    more = briefqa.run(
                                        brand_name=brand, seed_topic=opp.get("core_topic", ""),
                                        fanout_queries=fo_sel,
                                        grounding_bundle=st.session_state.get("grounding_bundle") or {},
                                        n=6, model=st.session_state.get("model", "opus"))
                                pool.extend([m for m in more if m not in pool])
                                st.session_state.brief_pool = pool
                                nxt = next((j for j in range(len(pool)) if j not in used), None)
                            except Exception:  # noqa: BLE001
                                nxt = None
                        if nxt is not None:
                            slots[si] = nxt
                            st.session_state.brief_slots = slots
                            st.rerun()
                    ans = st.text_area(f"Answer {si+1}", key=f"qa_ans_{pidx}", height=80,
                                       label_visibility="collapsed",
                                       placeholder="First-party detail (optional)…")
                    if ans.strip():
                        pairs.append(f"Q: {q}\nA: {ans.strip()}")
                st.session_state.topic_qa = "\n\n".join(pairs)
            else:
                st.write("Optionally answer up to 3 of this topic's AI-search prompts with first-party "
                         "detail (real numbers, named venues, specifics). Leave blank to skip.")
                plist = (opp.get("prompts") or [])[:3] or [
                    "Anything specific to emphasize about this topic?"]
                pairs = []
                for i, q in enumerate(plist):
                    ans = st.text_area(f"Q{i+1}. {q}", key=f"qa_{i}", height=80)
                    if ans.strip():
                        pairs.append(f"Q: {q}\nA: {ans.strip()}")
                st.session_state.topic_qa = "\n\n".join(pairs)
        nav()

    # -------------------------------------------------- cta
    elif key == "cta":
        opp = st.session_state.get("selected_opp", {})
        st.write("Choose a call to action, click one to continue, or write your own below.")
        cur = st.session_state.get("cta", "")
        c1, c2 = st.columns(2)
        for i, opt in enumerate(CTA_OPTIONS):
            col = c1 if i % 2 == 0 else c2
            picked = opt == cur
            if col.button((" " if picked else "") + opt, use_container_width=True, key=f"cta_{i}"):
                st.session_state.cta = opt
                goto(st.session_state.step + 1)
                st.rerun()
        st.markdown("")
        custom = st.text_input("Prefer your own? Write a custom CTA",
                               value=cur if cur not in CTA_OPTIONS else "",
                               placeholder=f"e.g. Reserve your suite  (objective: {opp.get('business_objective','')})")
        if custom.strip():
            st.session_state.cta = custom.strip()
        st.caption("Leave everything blank to auto-derive the CTA from the business objective.")
        nav(next_label="Ready to generate ")

    # -------------------------------------------------- generate
    elif key == "generate":
        opp = st.session_state.get("selected_opp"); client = st.session_state.get("client")
        mode = st.session_state.get("mode", "create")
        if not opp or not client:
            st.warning("Missing a selected topic or business. Go back.")
        else:
            st.write(f"**Business:** {client['name']} · **Topic:** {opp['core_topic']}")
            st.write(f"**Format:** {st.session_state.get('article_type')} · "
                     f"**Language:** {st.session_state.get('output_language')}")
            if mode == "optimize":
                st.write(f"**Optimizing:** {st.session_state.get('page_url','')}")
            n_enh = len(st.session_state.get("applied_enhancements") or [])
            if n_enh:
                st.info(f" This run will fold in {n_enh} applied enhancement(s) from the reasoning panel.")
            # content cache: replay an identical configuration instantly
            ckin = content_cache_key(opp, client, mode)
            if st.session_state.get("content_key") != ckin:
                st.session_state.content_key = ckin
                bundle_c, cts = cache.load("content", ckin)
                if bundle_c:
                    for _k in _CONTENT_KEYS:
                        st.session_state[_k] = bundle_c.get(_k)
                    st.session_state.content_ts = cts
                else:
                    for _k in _CONTENT_KEYS:
                        st.session_state.pop(_k, None)
                    st.session_state.content_ts = None
            lbl = "Research, generate & KAIROS-score" if mode == "create" else "Audit, rewrite & KAIROS-score"
            action = ui.gen_status_bar(
                has_data=bool(st.session_state.get("generated_md")),
                generated_at=st.session_state.get("content_ts"), key="content",
                generate_label=lbl, regenerate_label="Regenerate",
                busy_hint="~3–4 minutes · research, write, KAIROS score")
            if st.session_state.get("generated_md"):
                st.caption("Draft is ready, continue to **Review**. Validation & scoring are optional and "
                           "run on demand there, so this step stays fast.")
            if action:
                scope = f"{client['id']}/primary"
                with st.status("Working…", expanded=True) as status:
                    st.write("① Preparing public-web grounding…" if is_llm()
                             else "① Retrieving grounding context from Odin…")
                    try:
                        bundle = (st.session_state.get("grounding_bundle")
                                  or get_grounding(scope, opp["core_topic"],
                                                   hints=opp.get("entities")))
                    except odin.OdinAuthError as e:
                        st.session_state.odin_conn = {"ok": False, "needs_reauth": True, "message": str(e)}
                        status.update(label="Odin sign-in needed", state="error")
                        st.error(str(e)); st.stop()
                    # Fold the editor's first-party answers into the grounding bundle as sourced
                    # atoms so generation AND validation treat them as citable grounding.
                    bundle = prompt.merge_author_answers(bundle, st.session_state.get("topic_qa", ""))
                    st.session_state.grounding_bundle = bundle
                    if is_llm():
                        st.write("   Grounding from public sources (business not in Odin).")
                    else:
                        st.write(f"   {sum(len(v) for v in bundle.values() if isinstance(v, list))} grounded nodes.")
                    # For a press release, consult prior off-graph artifacts so the draft matches
                    # voice and never re-announces an existing story (guarded; Odin businesses only).
                    art_brief_text = ""
                    if eff_type() == "Press Release" and not is_llm():
                        try:
                            art_brief_text = artifacts.render_pr_artifact_brief(get_pr_artifact_brief(scope))
                        except Exception:  # noqa: BLE001, never block generation on the artifact read
                            art_brief_text = ""
                    st.write("② Assembling workflow prompt…")
                    try:  # real internal-link targets from the client's sitemap (best-effort)
                        links = get_internal_links(client, bundle)
                    except Exception:  # noqa: BLE001
                        links = []
                    if links:
                        st.write(f"   {len(links)} real internal-link targets from the sitemap.")
                    fp = prompt.build_prompt(
                        opp, mode=mode, brand_name=client["name"],
                        brand_voice=st.session_state.get("brand_voice_text", ""),
                        article_type=eff_type(),
                        target_audience=st.session_state.get("target_audience", ""),
                        cta=st.session_state.get("cta", ""), topic_qa=st.session_state.get("topic_qa", ""),
                        output_language=st.session_state.get("output_language", "English"),
                        grounding_bundle=bundle,
                        crawl_snapshot=st.session_state.get("crawl") if mode == "optimize" else None,
                        optimization_plan=st.session_state.get("opt_plan", "") if mode == "optimize" else "",
                        fanout_queries=st.session_state.get("fanout_selected"),
                        applied_enhancements=st.session_state.get("applied_enhancements"),
                        artifact_brief=art_brief_text,
                        author=st.session_state.get("author"),
                        brand_safety=st.session_state.get("brand_safety"),
                        internal_links=links)
                    st.session_state.final_prompt = fp
                    model = st.session_state.get("model", "opus")
                    at = eff_type()
                    lang = st.session_state.get("output_language", "English")
                    try:
                        import time as _time
                        _t0 = _time.time()
                        md = ui.run_with_progress(
                            lambda: generate.generate(fp, model=model), expected_seconds=210,
                            label="③ Research + write + KAIROS score/improve")
                        _dur = round(_time.time() - _t0, 1)
                        st.session_state.generated_md = md
                        sec_now = docs.split_sections(md)
                        st.session_state.content_blocks = docs.split_blocks(sec_now["publish_content"])
                        # Validation + scoring are now an optional, on-demand step in Review, so
                        # the draft lands fast. Clear any prior validation + enhancement state.
                        for _k in _VAL_KEYS:
                            st.session_state.pop(_k, None)
                        st.session_state.applied_enhancements = []
                        st.session_state.dismissed_enh = []
                        st.session_state.content_ts = cache.save(
                            "content", ckin, {k: st.session_state.get(k) for k in _CONTENT_KEYS})
                        # instant deterministic gates + observability (findings 13, 20)
                        try:
                            _pf = gates.run_gates(
                                sec_now["publish_content"], article_type=at,
                                restricted_terms=(st.session_state.get("brand_safety") or {}).get("restricted_terms"),
                                primary_keyword=(opp.get("keywords") or [""])[0] if opp.get("keywords") else "",
                                output_language=lang)
                            record_piece(client, opp, at)
                            runlog.append_run({
                                "client": client.get("name"), "format": at, "model": model,
                                "mode": mode, "duration_s": _dur, "cache_hit": False,
                                "word_count": _pf.get("word_count"), "grade": _pf.get("grade"),
                                "gates_failed": _pf.get("failed"), "gates_passed": _pf.get("passed"),
                                "topic": opp.get("core_topic")})
                        except Exception:  # noqa: BLE001 — telemetry must never block
                            pass
                        status.update(label="Publish-ready draft is ready", state="complete")
                        goto(step + 1); st.rerun()
                    except Exception as e:  # noqa: BLE001
                        status.update(label="Generation failed", state="error"); st.error(str(e))
            with st.expander("Preview assembled prompt"):
                st.code((st.session_state.get("final_prompt") or "generate to see the prompt")[:9000])
        nav(next_ok=False)

    # -------------------------------------------------- review
    elif key == "review":
        md = st.session_state.get("generated_md")
        if not md:
            st.warning("Nothing generated yet. Go back to Generate.")
        else:
            opp = st.session_state.get("selected_opp", {}); client = st.session_state.get("client", {})
            at = eff_type()
            lang = st.session_state.get("output_language", "English")
            brand = client.get("name", "Business"); topic = opp.get("core_topic", "")
            slug = docs.safe_slug(topic or "content"); sec = docs.split_sections(md)
            vmd = st.session_state.get("validation_md", "")
            vparts = {s: docs.extract_fence(vmd, s) for s in validation.SECTIONS}
            blocks = st.session_state.get("content_blocks") or docs.split_blocks(sec["publish_content"])
            recs_by_idx = {r["index"]: r for r in (st.session_state.get("block_records") or [])}
            overall = st.session_state.get("overall_block_score")

            # --- always-on instant quality gates + fact-check status + cannibalization ---
            pf = preflight_gates(sec["publish_content"], opp, at)
            _gb = st.session_state.get("grounding_bundle") or {}
            sld = schema_ld.build_all(
                sec["publish_content"], article_type=at, brand_name=brand, topic=topic,
                author=st.session_state.get("author"),
                publisher_url=_site_url_for(client, _gb) or None,
                grounding_bundle=_gb,
                url=st.session_state.get("page_url") if st.session_state.get("mode") == "optimize" else None,
                language=lang)
            render_quality_panel(pf, opp, client)

            # --- optional validation & scoring (kept OUT of generation so the draft lands fast) ---
            _val_done = overall is not None or bool(vmd)
            if not _val_done:
                vc1, vc2 = st.columns([3, 1.3])
                vc1.markdown("<div class='cs-genstamp'><span class='dot'></span> Draft is ready. "
                             "Per-paragraph validation, the KAIROS scorecard and competitive audit are "
                             "<b>optional</b> and run on demand (2-4 min).</div>", unsafe_allow_html=True)
                if vc2.button("Run validation & scoring", type="primary", use_container_width=True, key="run_val"):
                    with st.spinner("Fact-check + paragraph validation + enterprise audit + advisor (2-4 min)…"):
                        br, vmd2, e2, blks, fc2 = validate_suite(
                            sec["publish_content"], opp, client,
                            st.session_state.get("grounding_bundle") or {},
                            st.session_state.get("model", "opus"), at, lang)
                    st.session_state.block_records = br
                    st.session_state.validation_md = vmd2
                    st.session_state.enhancements = e2
                    st.session_state.content_blocks = blks
                    st.session_state.factcheck = fc2
                    st.session_state.overall_block_score = blockval.overall_score(br)
                    st.session_state.dismissed_enh = []
                    st.session_state.content_ts = cache.save(  # re-cache with validation filled in
                        "content", content_cache_key(opp, client, st.session_state.get("mode", "create")),
                        {k: st.session_state.get(k) for k in _CONTENT_KEYS})
                    st.rerun()
                st.divider()

            tabs = st.tabs(["Publish-Ready Content", "Reasoning & Enhancements",
                            "KAIROS Score & Audit", "Competitive Intelligence",
                            "Governance & Certification", "SEO & Ops Pack", "Full Markdown"])
            with tabs[0]:
                if overall is not None:
                    st.markdown(
                        f"**Overall validation score: {overall}/100** "
                        f"<span style='color:#4B5563;font-size:12px'>· average of "
                        f"{len(recs_by_idx)} block scores · click the ⓘ beside any block for its "
                        f"validation checklist &amp; CMG graph</span>", unsafe_allow_html=True)
                    st.divider()
                render_publish_blocks(blocks, recs_by_idx)
            with tabs[1]:
                if st.session_state.get("validation_stale"):
                    st.warning("You applied an enhancement, the relationship graph, per-paragraph "
                               "checks and scores below still reflect the previous draft. Re-validate "
                               "to refresh them against the edited content.")
                    if st.button(" Re-validate edited content", type="primary", key="reval"):
                        with st.spinner("Re-validating the edited content (2–4 min)…"):
                            br, vmd, e2, blks, fc = validate_suite(
                                sec["publish_content"], opp, client,
                                st.session_state.get("grounding_bundle") or {},
                                st.session_state.get("model", "opus"), at, lang)
                        st.session_state.block_records = br
                        st.session_state.validation_md = vmd
                        st.session_state.enhancements = e2
                        st.session_state.content_blocks = blks
                        st.session_state.factcheck = fc
                        st.session_state.overall_block_score = blockval.overall_score(br)
                        st.session_state.dismissed_enh = []
                        st.session_state.validation_stale = False
                        st.rerun()
                    st.divider()
                if is_llm():
                    st.markdown("#### Public-web sources used")
                    st.caption("This business is not in Odin, there is no memory graph. The content is "
                               "grounded in public sources cited per paragraph (open any ⓘ) and in "
                               "Competitive Intelligence.")
                else:
                    st.markdown("#### Entities & relationships from Odin, full grounding graph")
                _bundle = st.session_state.get("grounding_bundle") or {}
                _used = content_used_labels(st.session_state.get("block_records") or [])
                gnodes, grels, gtotal, gused = bundle_graph(_bundle, _used)
                if gnodes:
                    st.markdown(
                        f"<div style='background:#FFFFFF;border:1px solid #E5E7EB;border-radius:10px;"
                        f"padding:8px'>{ui.grounding_graph_svg(gnodes, grels, width=760, height=470)}</div>",
                        unsafe_allow_html=True)
                    st.caption(
                        f"This is the **full Odin subgraph supplied to generation**: "
                        f"**{gtotal} entities · {len(grels)} relationships**. "
                        f"Solid navy = referenced in this draft ({gused}); hollow = retrieved and "
                        f"available but not cited yet. Showing {len(gnodes)} of {gtotal}. "
                        f"Open any paragraph's ⓘ for its per-block sources & coverage.")
                else:
                    # fallback: aggregate the per-block cited nodes if the bundle is unavailable
                    fnodes, frels = whole_content_graph(st.session_state.get("block_records") or [])
                    if fnodes:
                        st.markdown(
                            f"<div style='background:#FFFFFF;border:1px solid #E5E7EB;border-radius:10px;"
                            f"padding:8px'>{ui.subgraph_svg(fnodes, frels, width=760, height=380)}</div>",
                            unsafe_allow_html=True)
                        st.caption("Aggregated from the "
                                   + ("public entities/sources" if is_llm() else "CMG nodes")
                                   + " each paragraph cited.")
                    else:
                        st.caption("No grounded entities were recorded for this content.")
                st.divider()
                render_enhancements(st.session_state.get("grounding_bundle") or {},
                                    sec["publish_content"], client, st.session_state.get("model", "opus"))
            with tabs[2]:
                st.markdown(sec["score_report"] or "_(no score report)_")
                if vparts.get("KAIROS_VALIDATION"):
                    st.divider()
                    st.markdown("#### KAIROS whole-content validation")
                    st.markdown(vparts["KAIROS_VALIDATION"])
            tabs[3].markdown(vparts.get("COMPETITIVE_INTEL") or "_(not available)_")
            tabs[4].markdown(vparts.get("GOVERNANCE") or "_(not available)_")
            with tabs[5]:
                st.markdown(sec["ops_pack"] or "_(no ops pack)_")
                st.divider()
                st.markdown("#### Structured data (JSON-LD)")
                if sld.get("blocks"):
                    st.caption("Auto-generated from the finished content + grounding — paste into the "
                               "page `<head>`. Included: "
                               + ", ".join(b["type"] for b in sld["blocks"]) + ".")
                    st.code(sld["script_html"], language="html")
                else:
                    st.caption("No structured data could be derived for this content.")
            tabs[6].code(md, language="markdown")

            # ---- downloads (no approval gate) ----
            st.divider()
            st.markdown("**Download**")
            content_md = sec["publish_content"]
            cols = st.columns(4)
            try:
                cols[0].download_button(" Content (PDF)",
                    docs.markdown_to_pdf(content_md, brand=brand, topic=topic, article_type=at, language=lang),
                    file_name=f"{slug}.pdf", mime="application/pdf", type="primary")
            except Exception as e:  # noqa: BLE001
                st.error(f"Content PDF failed: {e}")
            try:
                cols[1].download_button(" Content (Word)",
                    docs.markdown_to_docx(content_md, brand=brand, topic=topic, article_type=at, language=lang),
                    file_name=f"{slug}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            except Exception as e:  # noqa: BLE001
                st.error(f"DOCX failed: {e}")
            cols[2].download_button(" Content (Markdown)", content_md.encode("utf-8"),
                                    file_name=f"{slug}.md", mime="text/markdown")
            # --- single enterprise deliverable: content + gates + fact-check + scorecard +
            #     competitive evidence + governance + ops pack + JSON-LD (finding 15) ---
            fc = st.session_state.get("factcheck")
            gates_md = "\n".join(
                f"- {_GATE_ICON.get(g['status'],'')} **{g['label']}** — {g['detail']}" for g in pf["gates"])
            fc_md = ""
            if fc:
                fc_md = f"**Fact-check gate:** {'PASS' if fc.get('gate_pass') else 'FAIL'} — {fc.get('summary','')}"
                if fc.get("unverified"):
                    fc_md += "\n\nUnverified claims:\n" + "\n".join(
                        f"- {c.get('claim','')}" for c in fc["unverified"])
            schema_md = ("```html\n" + sld["script_html"] + "\n```") if sld.get("blocks") else ""
            report_md = "\n\n".join(x for x in [
                f"# {topic}\n\n{content_md}",
                "# Quality Gates\n\n" + gates_md + (f"\n\n{fc_md}" if fc_md else ""),
                f"# KAIROS Score Report\n\n{sec['score_report']}" if sec.get("score_report") else "",
                f"# KAIROS Whole-Content Validation\n\n{vparts.get('KAIROS_VALIDATION','')}" if vparts.get("KAIROS_VALIDATION") else "",
                f"# Competitive Intelligence & Information Gain\n\n{vparts.get('COMPETITIVE_INTEL','')}" if vparts.get("COMPETITIVE_INTEL") else "",
                f"# Enterprise Governance & Certification\n\n{vparts.get('GOVERNANCE','')}" if vparts.get("GOVERNANCE") else "",
                f"# SEO & Ops Pack\n\n{sec['ops_pack']}" if sec.get("ops_pack") else "",
                f"# Structured Data (JSON-LD)\n\n{schema_md}" if schema_md else ""] if x)
            try:
                cols[3].download_button(" Enterprise report (PDF)",
                    docs.markdown_to_pdf(report_md, brand=brand,
                                         topic=f"{topic} — Content, Validation & Certification",
                                         article_type=at, language=lang),
                    file_name=f"{slug}-enterprise-report.pdf", mime="application/pdf")
            except Exception as e:  # noqa: BLE001
                st.error(f"Report PDF failed: {e}")

            st.divider()
            r1, r2 = st.columns([1, 3])
            if r1.button(" Regenerate"):
                goto(steps.index("generate")); st.rerun()
            if r2.button(" Start over"):
                for k in list(st.session_state.keys()):
                    if k != "model":
                        del st.session_state[k]
                goto(0); st.rerun()
        nav(next_ok=False)

# ---- product footer (renders full-width beneath the workflow) ----
ui.footer()
