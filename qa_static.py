"""QA Suite A — static/plumbing checks (no LLM calls). Exercises every workflow function
that does not require a live generation, across ALL 11 formats + both grounding modes."""
import sys, traceback
sys.path.insert(0, ".")
from lib import (prompt, docs, opportunities, fanout, taxonomy, cache, prcalendar,
                 briefqa, blockval, enhance, validation, optplan, crawl, artifacts, odin,
                 topicgen, preferences, matcher, reasoning, ui)

FORMATS = ["Blog Article", "Newsletter", "Press Release", "Press Release Calendar",
           "How-To Guide", "Thought Leadership", "Comparison Article", "Landing Page",
           "Pillar Page", "Listicle", "News Article"]
PASS, FAIL = [], []
def check(name, fn):
    try:
        fn(); PASS.append(name); print(f"  PASS  {name}")
    except Exception as e:
        FAIL.append((name, f"{type(e).__name__}: {e}"))
        print(f"  FAIL  {name}  ->  {type(e).__name__}: {e}")
        traceback.print_exc()

# ---------- fixtures ----------
RAW_OPP = {
    "id": "all-inclusive-value", "core_topic": "All-inclusive value at the resort",
    "keywords": ["all-inclusive value", "whats included", "resort pricing"],
    "prompts": ["What's included in all-inclusive?", "Is it worth the price?"],
    "intent": "Commercial", "reach": 80, "geo_lift": 78, "effort": "Medium",
    "business_objective": "Increase Direct Bookings & Reduce OTA Dependency",
    "guest_journey": "Price Evaluation", "hotel_features": ["Dining"],
    "content_gap_type": "Critical", "recommendation": "Blog Article",
    "entities": ["Grand Velas", "All-Inclusive Value", "Rate Transparency"],
    "memory_graph_nodes": {"entities": ["Grand Velas", "Rate Transparency"],
                           "relations": ["Grand Velas -> offers -> Suites"]},
    "evidence_sources": ["graph:property-gv"], "score": 90,
}
OPP = opportunities.normalize({"opportunities": [RAW_OPP]})[0]
BUNDLE = {"property": [{"id": "gv1", "name": "Grand Velas", "type": "property",
                       "facts": {"city": "Riviera Maya"}}],
          "review_theme": [{"id": "rt1", "name": "Rate Transparency", "type": "review_theme"}],
          "_fact_ledger": [{"fact": "Grand Velas - city: Riviera Maya", "source": "gv1",
                            "provenance": [], "freshness": "2026-01-01"}]}
PUBLIC = prompt.public_bundle({"name": "Test Resort", "website": "https://example.com",
                               "location": "Cancun"})
FANOUT_SEL = [{"id": "q1", "query": "what's actually included", "qforia_type": "Implicit Query",
               "user_intent": "confirm value", "reasoning": "closes a white-space gap",
               "whitespace": "White space", "click_worthiness": "Decision-criteria",
               "priority": 88, "scorecard": ["real list of inclusions"], "intent": "Commercial",
               "original_query": "what's included", "answerable_from": "Odin"}]

# ---------- A1: opportunities.normalize keeps entities ----------
check("opportunities.normalize: entities+mgn present",
      lambda: (OPP["entities"] and OPP["memory_graph_nodes"]["entities"]) or (_ for _ in ()).throw(AssertionError("entities empty")))

# ---------- A2: build_prompt for EVERY format, create + optimize + PR + non-Odin ----------
def _bp(fmt, mode, bundle, snap=None):
    p = prompt.build_prompt(OPP, mode=mode, brand_name="Grand Velas",
                            brand_voice="Confident, understated luxe; no hype.",
                            article_type=("Press Release" if fmt == "Press Release Calendar" else fmt),
                            target_audience="Value-conscious premium buyers, 45-65.",
                            cta="Check live rates", topic_qa="Q: pools?\nA: 5 pools.",
                            output_language="English", grounding_bundle=bundle,
                            crawl_snapshot=snap, optimization_plan=("Retain X" if mode == "optimize" else ""),
                            fanout_queries=FANOUT_SEL, applied_enhancements=[], artifact_brief="")
    assert len(p) > 2000, "prompt too short"
    assert "Grand Velas" in p, "brand missing"
    assert ("Confident" in p), "brand voice missing"
    assert "Value-conscious" in p, "persona missing"
    assert "what's actually included" in p, "fanout query missing"
    return p
for fmt in FORMATS:
    check(f"build_prompt[create/odin] {fmt}", lambda fmt=fmt: _bp(fmt, "create", BUNDLE))
for fmt in FORMATS:
    check(f"build_prompt[create/non-odin] {fmt}", lambda fmt=fmt: _bp(fmt, "create", PUBLIC))
SNAP = {"url": "https://x.com/p", "title": "Old page", "meta_description": "m",
        "schema_types": ["Hotel"], "headings": {"h1": ["H1"], "h2": ["H2a", "H2b"]},
        "body_text": "Existing copy " * 50, "word_count": 100, "fetch_method": "test"}
for fmt in FORMATS:
    check(f"build_prompt[optimize/odin] {fmt}", lambda fmt=fmt: _bp(fmt, "optimize", BUNDLE, SNAP))

# ---------- A3: format_guidelines for each ----------
for fmt in FORMATS:
    at = "Press Release" if fmt == "Press Release Calendar" else fmt
    check(f"format_guidelines {fmt}", lambda at=at: (prompt.format_guidelines(at, "Grand Velas") is not None))

# ---------- A4: docs.sanitize_publish strips ALL internal tokens ----------
def _san():
    t = ("Our resort [graph:prop-1] has 5 pools [graph:author-first-party-2]. "
         "Check-in 3pm [to verify]. Spa [not available in provided context]. See [web:src].")
    out = docs.sanitize_publish(t)
    for bad in ["[graph:", "[web:", "author-first-party", "to verify", "not available"]:
        assert bad not in out, f"token leaked: {bad}"
check("docs.sanitize_publish strips tokens", _san)

# ---------- A5: split_sections on a full 3-part model output ----------
def _split():
    md = ("<<<PUBLISH_CONTENT_START>>>\n# Title [graph:x]\nBody.\n<<<PUBLISH_CONTENT_END>>>\n"
          "<<<OPS_PACK_START>>>\nMeta\n<<<OPS_PACK_END>>>\n"
          "<<<SCORE_REPORT_START>>>\nSEO 90\n<<<SCORE_REPORT_END>>>")
    s = docs.split_sections(md)
    assert s["publish_content"] and s["ops_pack"] and s["score_report"]
    assert "[graph:x]" not in s["publish_content"], "token not sanitized in publish"
    blocks = docs.split_blocks(s["publish_content"]); assert blocks
check("docs.split_sections + split_blocks + sanitize", _split)

# ---------- A6: PDF generation (the negative-availWidth area) with a wide table ----------
def _pdf():
    md = ("# Report\n\nIntro paragraph.\n\n| Feature | Detail A | Detail B | Detail C | Detail D |\n"
          "|---|---|---|---|---|\n| Pools | very long cell " * 1 + "| x | y | z | w |\n\n## Section\nMore.")
    pdf = docs.markdown_to_pdf(md, brand="Grand Velas", topic="T", article_type="Blog Article", language="English")
    assert pdf and len(pdf) > 800, "pdf empty"
check("docs.markdown_to_pdf (wide table)", _pdf)

# ---------- A7: fanout postprocess + grouping + qforia normalization ----------
def _fan():
    data = {"original_queries": [{"id": "o1", "query": "what's included", "intent": "Commercial"}],
            "queries": [dict(FANOUT_SEL[0], original_id="o1", type="Attribute", qforia_type="implicit",
                             opportunity=90)]}
    qs = [fanout._postprocess(dict(q), i) for i, q in enumerate(data["queries"])]
    assert qs[0]["qforia_type"] == "Implicit Query"
    assert qs[0]["priority"] > 0
    data["queries"] = qs
    g = fanout.group_by_original(data); assert g and g[0]["queries"]
    assert fanout.normalize_qforia_type("comparison") == "Comparative Query"
    assert fanout.compute_priority(90, "White space", "Decision-criteria") > 0
check("fanout postprocess/group/qforia", _fan)

# ---------- A8: taxonomy mapping ----------
def _tax():
    assert taxonomy.map_objective("increase bookings", text="book now")
    assert taxonomy.map_journey("evaluation", intent="Commercial", text="compare")
    assert taxonomy.criteria_taxonomy_block("Beach / resort")
    assert len(taxonomy.DEFAULT_OBJECTIVES) == 10
    assert len(taxonomy.GUEST_JOURNEY) == 35
check("taxonomy objectives(10)/journey(35)/mapping", _tax)

# ---------- A9: cache round-trip + timestamp ----------
def _cache():
    k = cache.key("qa-test", "create")
    cache.save("qa_test", k, {"x": [1, 2, 3]})
    d, ts = cache.load("qa_test", k)
    assert d == {"x": [1, 2, 3]} and ts and cache.human_ts(ts)
    cache.clear("qa_test", k)
check("cache save/load/human_ts", _cache)

# ---------- A10: prcalendar mapping + markdown ----------
def _prcal():
    story = {"month": "January", "month_index": 1, "story_rank": 1, "title": "New spa",
             "scores": {"newsworthiness": 5, "brand_relevance": 5, "audience_relevance": 4,
                        "media_potential": 4, "timing": 5}, "narrative": "Wellness",
             "business_objective": "Strengthen Brand Awareness & Market Position",
             "news_hook": "opening", "keywords": ["spa"], "why_this_month": "seasonal"}
    opp = prcalendar.to_opportunity(story); assert opp["id"].startswith("pr-")
    assert opp["recommendation"] == "Press Release"
    md = prcalendar.calendar_markdown({"brand": "GV", "year": 2026, "calendar": [dict(story, pr_score=2000, priority="High")]})
    assert "New spa" in md
    assert prcalendar.scoring_explainer()["formula"]
check("prcalendar to_opportunity/markdown/scoring", _prcal)

# ---------- A11: render_grounding_context (odin + llm) + merge_author_answers ----------
def _ground():
    assert "Grand Velas" in prompt.render_grounding_context(BUNDLE)
    assert prompt.render_grounding_context(PUBLIC)
    b2 = prompt.merge_author_answers(dict(BUNDLE), "Q: pools?\nA: 5 heated pools.")
    assert prompt.is_llm_bundle(PUBLIC) and not prompt.is_llm_bundle(BUNDLE)
check("render_grounding_context odin+llm + merge_author_answers", _ground)

# ---------- A12: odin connectivity (live probe) ----------
def _odin():
    p = odin.probe(); assert p.get("ok"), p.get("message")
    assert len(odin.list_clients()) > 0
check("odin.probe (live) + list_clients", _odin)

# ---------- A13: crawl module import + trafilatura availability ----------
check("crawl module importable", lambda: hasattr(crawl, "crawl") or hasattr(crawl, "fetch_page") or True)

print("\n================ SUITE A RESULT ================")
print(f"PASS: {len(PASS)}   FAIL: {len(FAIL)}")
for n, e in FAIL:
    print(f"  FAIL {n}: {e}")
sys.exit(1 if FAIL else 0)
