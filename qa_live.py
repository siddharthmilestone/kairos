"""QA Suite B — live end-to-end pipelines against Odin + claude.
Covers Create/Optimize/PR paths x Odin/Non-Odin, and content generation across formats.
Uses haiku (tools-off) for bounded, deterministic runs — tests the full code path of every
workflow function. Prints PASS/FAIL with real evidence per step."""
import sys, time, json, traceback
sys.path.insert(0, ".")
from lib import (odin, topicgen, opportunities, fanout, briefqa, prompt, generate, docs,
                 validation, blockval, enhance, prcalendar, optplan, matcher, crawl, artifacts)

R = []
def step(name, fn):
    t0 = time.time()
    try:
        info = fn() or ""
        R.append((name, "PASS", info, time.time()-t0))
        print(f"[PASS {time.time()-t0:5.0f}s] {name}  {info}", flush=True)
        return True
    except Exception as e:
        R.append((name, "FAIL", f"{type(e).__name__}: {e}", time.time()-t0))
        print(f"[FAIL {time.time()-t0:5.0f}s] {name}  ->  {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        return False

def gen_content(opp, bundle, *, mode="create", fmt="Blog Article", snap=None, plan="", fo_sel=None):
    fp = prompt.build_prompt(opp, mode=mode, brand_name="Grand Velas Resorts",
                             brand_voice="Confident, understated luxe; no hype; never em dashes.",
                             article_type=fmt, target_audience="Value-conscious premium buyers 45-65.",
                             cta="Check live rates", topic_qa="Q: pools?\nA: 5 heated pools, adults-only option.",
                             output_language="English", grounding_bundle=bundle,
                             crawl_snapshot=snap, optimization_plan=plan, fanout_queries=fo_sel or [],
                             applied_enhancements=[], artifact_brief="")
    out = generate.generate(fp, model="haiku", timeout=600, allow_tools=False)
    sec = docs.split_sections(out)
    pub = sec["publish_content"]
    assert len(pub) > 400, "publish content too short"
    for bad in ["[graph:", "[web:", "author-first-party", "<<<PUBLISH", "Meta Title:"]:
        assert bad not in pub, f"leak in PART A: {bad}"
    assert "—" not in pub, "em dash leaked into content"
    return sec, pub

client = next(c for c in odin.list_clients() if "velas" in c["name"].lower())
scope = f"{client['id']}/primary"
CTX = {}

# ============ P1: CREATE / ODIN — full chain ============
def p1_grounding():
    b = odin.gather_grounding(scope, client["name"], light=True)
    n = sum(len(v) for k, v in b.items() if isinstance(v, list) and not k.startswith("_"))
    CTX["bundle"] = b; assert n > 0; return f"{n} nodes"
step("P1.1 grounding (Odin, light)", p1_grounding)

def p1_topics():
    _, data = topicgen.generate_topics(business_id=client["id"], business_name=client["name"],
        scope=scope, grounding_bundle=CTX["bundle"], n=6, model="haiku", use_cache=False)
    recs = opportunities.normalize(data); CTX["opp"] = recs[0]
    assert recs[0]["entities"], "no entities on topic (CMG diagram would be empty)"
    return f"{len(recs)} topics, entities={len(recs[0]['entities'])}"
step("P1.2 topic generation + entities", p1_topics)

def p1_fanout():
    d = fanout.run_fanout(opp=CTX["opp"], brand_name=client["name"], target_audience="families",
        output_language="English", grounding_bundle=CTX["bundle"], page_snapshot=None,
        depth=2, fanout_limit=14, model="haiku")
    assert len(d.get("original_queries", [])) >= 3, "originals missing"
    types = {q["qforia_type"] for q in d["queries"]}
    CTX["fo_sel"] = [q for q in d["queries"] if q.get("whitespace") == "White space"][:4] or d["queries"][:4]
    return f"{len(d['original_queries'])} originals, {len(d['queries'])} queries, types={len(types)}"
step("P1.3 fan-out (Qforia)", p1_fanout)

def p1_qa():
    pool = briefqa.run(brand_name=client["name"], seed_topic=CTX["opp"]["core_topic"],
        fanout_queries=CTX["fo_sel"], grounding_bundle=CTX["bundle"], n=6, model="haiku")
    assert pool and len(pool) >= 3; return f"{len(pool)} questions"
step("P1.4 brief Q&A", p1_qa)

def p1_content():
    sec, pub = gen_content(CTX["opp"], CTX["bundle"], fmt="Blog Article", fo_sel=CTX["fo_sel"])
    CTX["content"] = pub; CTX["blocks"] = docs.split_blocks(pub)
    assert pub.lstrip().startswith("#"), "no H1"
    assert sec["score_report"], "no score report"
    return f"pub={len(pub)}c, blocks={len(CTX['blocks'])}, ops={bool(sec['ops_pack'])}"
step("P1.5 content generation (Blog) + clean + sections", p1_content)

def p1_validation():
    vmd = validation.run_validation(publish_content=CTX["content"], brand_name=client["name"],
        article_type="Blog Article", output_language="English", grounding_bundle=CTX["bundle"],
        opportunity=CTX["opp"], model="haiku")
    assert vmd and len(vmd) > 100; return f"validation md {len(vmd)}c"
step("P1.6 enterprise validation (KVE)", p1_validation)

def p1_blockval():
    br = blockval.run(blocks=CTX["blocks"], brand_name=client["name"],
        brand_voice="Confident luxe", target_audience="premium buyers",
        opportunity=CTX["opp"], grounding_bundle=CTX["bundle"], model="haiku")
    sc = blockval.overall_score(br)
    assert br; return f"{len(br)} block records, overall={sc}"
step("P1.7 per-paragraph validation", p1_blockval)

def p1_enhance():
    enh = enhance.run(content=CTX["content"], brand_name=client["name"], opportunity=CTX["opp"],
        fanout_queries=CTX["fo_sel"], grounding_bundle=CTX["bundle"], model="haiku")
    return f"{len(enh)} enhancement suggestions"
step("P1.8 enhancement advisor", p1_enhance)

def p1_pdf():
    pdf = docs.markdown_to_pdf(CTX["content"], brand=client["name"], topic=CTX["opp"]["core_topic"],
        article_type="Blog Article", language="English")
    assert pdf and len(pdf) > 1000; return f"pdf {len(pdf)} bytes"
step("P1.9 PDF export", p1_pdf)

# ============ P2: CREATE / ODIN — format adaptation (reuse opp/fanout/bundle) ============
for fmt in ["Listicle", "How-To Guide", "Comparison Article"]:
    step(f"P2 content adaptation [{fmt}]",
         lambda fmt=fmt: (lambda r: f"pub={len(r[1])}c")(gen_content(CTX["opp"], CTX["bundle"], fmt=fmt, fo_sel=CTX["fo_sel"])))

# ============ P3: PR path ============
def p3_calendar():
    data = prcalendar.generate_calendar(brand_name=client["name"], grounding_bundle=CTX["bundle"],
        year=2027, model="haiku")
    assert data["calendar"]; CTX["pr_story"] = data["calendar"][0]
    return f"{len(data['calendar'])} stories"
step("P3.1 PR calendar generation", p3_calendar)

def p3_pr_content():
    opp = prcalendar.to_opportunity(CTX["pr_story"])
    opp = opportunities.normalize({"opportunities": [opp["_raw"] and opp]})[0] if False else opp
    sec, pub = gen_content(opp, CTX["bundle"], fmt="Press Release", fo_sel=[])
    assert "FOR IMMEDIATE RELEASE" in pub.upper() or "immediate release" in pub.lower(), "no PR structure"
    return f"PR pub={len(pub)}c"
step("P3.2 Press Release content", p3_pr_content)

# ============ P4: Non-Odin (public web / LLM) ============
def p4_nonodin():
    pub_bundle = prompt.public_bundle({"name": "Seaside Boutique Hotel",
        "website": "https://example.com", "location": "Santa Monica, CA"})
    _, data = topicgen.generate_topics(business_id="seaside", business_name="Seaside Boutique Hotel",
        scope="", grounding_bundle=pub_bundle, n=5, model="haiku", use_cache=False)
    recs = opportunities.normalize(data); assert recs
    sec, pub = gen_content(recs[0], pub_bundle, fmt="Blog Article", fo_sel=[])
    CTX["nonodin_ok"] = True
    return f"{len(recs)} topics, content={len(pub)}c"
step("P4 Non-Odin: public topics + content", p4_nonodin)

# ============ P5: Optimize path ============
def p5_crawl():
    snap = crawl.crawl("https://www.grandvelas.com/")
    assert snap.get("body_text"), "crawl empty"
    CTX["snap"] = snap
    return f"words={snap.get('word_count','?')}, schema={snap.get('schema_types')}"
step("P5.1 crawl live page", p5_crawl)

def p5_match():
    terms = crawl.page_terms(CTX["snap"])
    scored = matcher.match([CTX["opp"]], terms, top_k=5)
    assert scored; return f"page_terms={len(terms)}, matched={len(scored)}, top_score={scored[0].get('match_score')}"
step("P5.2 matcher (topic vs page)", p5_match)

def p5_optplan():
    plan = optplan.run_plan(brand_name=client["name"], article_type="Web Page",
        opportunity=CTX["opp"], crawl_snapshot=CTX["snap"], grounding_bundle=CTX["bundle"], model="haiku")
    for tag in ["RETAIN", "ENHANCE", "PRUNE", "CREATE"]:
        assert docs.extract_fence(plan, tag) is not None or tag in plan, f"plan missing {tag}"
    CTX["plan"] = plan; return f"plan {len(plan)}c"
step("P5.3 optimize plan (Retain/Enhance/Prune/Create)", p5_optplan)

def p5_opt_content():
    sec, pub = gen_content(CTX["opp"], CTX["bundle"], mode="optimize", fmt="Web Page",
        snap=CTX["snap"], plan=CTX.get("plan", ""), fo_sel=CTX["fo_sel"])
    return f"optimize pub={len(pub)}c"
step("P5.4 optimize content generation", p5_opt_content)

print("\n================ SUITE B RESULT ================")
p = sum(1 for _, s, _, _ in R if s == "PASS"); f = sum(1 for _, s, _, _ in R if s == "FAIL")
print(f"PASS: {p}   FAIL: {f}")
for n, s, info, _ in R:
    if s == "FAIL":
        print(f"  FAIL {n}: {info}")
print("QA_LIVE_DONE")
