"""Kairos as a local HTTP service.

Exposes the same `lib/` functions the Streamlit stepper uses, so the agentic chat
runs the *identical* prompts, schemas and Odin grounding — no second
implementation to drift out of sync.

Stdlib only (no new deps in the venv). Run:

    .venv/bin/python kairos_service.py            # port 8534
"""
from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib import (  # noqa: E402
    blockval, briefqa, cache, crawl, docs, enhance, fanout, generate, odin,
    opportunities, optplan, prcalendar, preferences, prompt, prcalendar as _prc, taxonomy, topicgen,
)

PORT = int(os.environ.get("KAIROS_PORT", "8534"))

# Speed policy for the chat surface. The stepper lets the user pick; here the
# structured/planning steps are pinned to the fast model and only the final draft
# uses the quality model. This is the single biggest lever on perceived latency.
FAST = "haiku"
CONTENT = "sonnet"

FORMATS = ["Blog Article", "Newsletter", "Press Release", "Press Release Calendar",
           "How-To Guide", "Thought Leadership", "Comparison Article", "Landing Page",
           "Pillar Page", "Listicle", "News Article"]

CTA_OPTIONS = ["Book your stay", "Check availability & rates", "Request a proposal",
               "Explore offers & packages", "Contact our concierge", "Plan your event"]

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    """One in-flight computation per cache key — a second caller waits and then
    reads the cache instead of paying for the same generation twice."""
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def cached(kind: str, key: str, produce, *, force: bool = False) -> tuple[Any, str | None, bool]:
    """Return (data, generated_at, was_cached)."""
    if not force:
        data, ts = cache.load(kind, key)
        if data is not None:
            return data, ts, True
    with _lock_for(f"{kind}:{key}"):
        if not force:
            data, ts = cache.load(kind, key)
            if data is not None:
                return data, ts, True
        data = produce()
        ts = cache.save(kind, key, data)
        return data, ts, False


# --------------------------------------------------------------------- handlers

def h_health(_: dict) -> dict:
    return {"ok": True, "formats": FORMATS, "ctas": CTA_OPTIONS,
            "fast_model": FAST, "content_model": CONTENT}


def h_clients(_: dict) -> dict:
    return {"clients": odin.list_clients()}


def h_grounding(b: dict) -> dict:
    """Grounding bundle for a business + topic. `light` skips 1-hop traversal."""
    scope = b["scope"]
    topic = b.get("topic") or ""
    light = bool(b.get("light", True))
    k = cache.key("grounding", scope, topic, "light" if light else "deep")
    data, ts, was = cached(
        "grounding", k,
        lambda: odin.gather_grounding(scope, topic, entity_hints=b.get("hints") or [],
                                      kind=b.get("kind", "hospitality"), light=light),
        force=bool(b.get("force")))
    ledger = data.get("_fact_ledger") or []
    return {"bundle": data, "generated_at": ts, "cached": was,
            "stats": {"entities": sum(len(v) for k2, v in data.items() if k2 != "_fact_ledger"),
                      "facts": len(ledger),
                      "types": sorted(k2 for k2 in data if k2 != "_fact_ledger")}}


def h_topics(b: dict) -> dict:
    scope = b["scope"]
    bundle = b.get("bundle") or h_grounding({"scope": scope, "topic": b.get("seed", ""),
                                             "kind": b.get("kind", "hospitality")})["bundle"]
    n = int(b.get("n", 12))
    k = cache.key("topics", b["business_id"], b.get("page_url") or "", n)

    def produce():
        # generate_topics returns (json_path, parsed_dict) — keep only the payload.
        _, parsed = topicgen.generate_topics(
            business_id=b["business_id"], business_name=b["business_name"], scope=scope,
            grounding_bundle=bundle, page_snapshot=b.get("page_snapshot"),
            n=n, model=b.get("model", FAST), use_cache=True)
        return parsed

    data, ts, was = cached("topics", k, produce, force=bool(b.get("force")))
    topics = opportunities.normalize(data)
    return {"topics": topics, "generated_at": ts, "cached": was}


def h_fanout(b: dict) -> dict:
    opp = b["opportunity"]
    k = cache.key("fanout", b["brand_name"], opp.get("id") or opp.get("core_topic"),
                  b.get("depth", 2), b.get("limit", 20))
    data, ts, was = cached(
        "fanout", k,
        lambda: fanout.run_fanout(
            opp=opp, brand_name=b["brand_name"],
            target_audience=b.get("target_audience", ""),
            output_language=b.get("output_language", "English"),
            grounding_bundle=b["bundle"], page_snapshot=b.get("page_snapshot"),
            depth=int(b.get("depth", 2)), fanout_limit=int(b.get("limit", 20)),
            model=b.get("model", FAST)),
        force=bool(b.get("force")))
    return {"fanout": data, "generated_at": ts, "cached": was}


def h_prcalendar(b: dict) -> dict:
    year = int(b.get("year") or datetime.now(timezone.utc).year + 1)
    k = cache.key("prcal", b["brand_name"], year)
    data, ts, was = cached(
        "prcal", k,
        lambda: prcalendar.generate_calendar(
            brand_name=b["brand_name"], grounding_bundle=b["bundle"], year=year,
            model=b.get("model", FAST), artifact_brief=b.get("artifact_brief", ""),
            lean=True),
        force=bool(b.get("force")))
    return {"calendar": data, "generated_at": ts, "cached": was,
            "scoring": prcalendar.scoring_explainer()}


def h_pr_enrich(b: dict) -> dict:
    story = prcalendar.enrich_story(
        brand_name=b["brand_name"], grounding_bundle=b["bundle"], story=b["story"],
        artifact_brief=b.get("artifact_brief", ""), model=b.get("model", FAST),
        year=b.get("year"))
    return {"story": story}


def h_briefqa(b: dict) -> dict:
    k = cache.key("briefqa", b["brand_name"], b.get("seed_topic", ""), b.get("n", 6))
    data, ts, was = cached(
        "briefqa", k,
        lambda: briefqa.run(
            brand_name=b["brand_name"], seed_topic=b.get("seed_topic", ""),
            fanout_queries=b.get("fanout_queries") or [], grounding_bundle=b["bundle"],
            n=int(b.get("n", 6)), model=b.get("model", FAST)),
        force=bool(b.get("force")))
    return {"questions": data, "generated_at": ts, "cached": was}


def h_crawl(b: dict) -> dict:
    url = b["url"]
    k = cache.key("crawl", url)
    data, ts, was = cached("crawl", k, lambda: crawl.crawl(url), force=bool(b.get("force")))
    return {"snapshot": data, "generated_at": ts, "cached": was}


def h_optplan(b: dict) -> dict:
    k = cache.key("optplan", b["brand_name"], (b.get("opportunity") or {}).get("core_topic", ""),
                  (b.get("crawl_snapshot") or {}).get("url", ""))
    data, ts, was = cached(
        "optplan", k,
        lambda: optplan.run_plan(
            brand_name=b["brand_name"], article_type=b.get("article_type", "Blog Article"),
            opportunity=b.get("opportunity") or {}, crawl_snapshot=b.get("crawl_snapshot") or {},
            grounding_bundle=b["bundle"], model=b.get("model", FAST)),
        force=bool(b.get("force")))
    return {"plan": data, "generated_at": ts, "cached": was}


def h_preferences(b: dict) -> dict:
    k = cache.key("prefs", b["business_name"])
    data, ts, was = cached(
        "prefs", k,
        lambda: preferences.generate_preferences(
            business_name=b["business_name"], grounding_bundle=b["bundle"],
            model=b.get("model", FAST)),
        force=bool(b.get("force")))
    return {"preferences": data, "generated_at": ts, "cached": was}


def h_generate(b: dict) -> dict:
    """Final content draft — the one step that uses the quality model."""
    opp = b.get("opportunity") or {}
    p = prompt.build_prompt(
        opp, mode=b.get("mode", "create"), brand_name=b["brand_name"],
        brand_voice=b.get("brand_voice", ""), article_type=b.get("article_type", "Blog Article"),
        target_audience=b.get("target_audience", ""), cta=b.get("cta", ""),
        topic_qa=b.get("topic_qa", ""), output_language=b.get("output_language", "English"),
        grounding_bundle=b["bundle"], fanout_queries=b.get("fanout_queries"),
        page_snapshot=b.get("page_snapshot"), plan=b.get("plan"),
        enhancements=b.get("enhancements"))
    k = cache.key("content", b["brand_name"], opp.get("core_topic", ""),
                  b.get("article_type", ""), b.get("cta", ""), len(b.get("topic_qa", "")))
    data, ts, was = cached(
        "content", k,
        lambda: generate.generate(p, model=b.get("model", CONTENT), timeout=900),
        force=bool(b.get("force")))
    return {"content": data, "generated_at": ts, "cached": was}


def h_validate(b: dict) -> dict:
    recs = blockval.run(
        blocks=b["blocks"], brand_name=b["brand_name"], brand_voice=b.get("brand_voice", ""),
        target_audience=b.get("target_audience", ""), opportunity=b.get("opportunity") or {},
        grounding_bundle=b["bundle"], model=b.get("model", FAST))
    return {"records": recs, "overall": blockval.overall_score(recs)}


def h_enhance(b: dict) -> dict:
    return {"suggestions": enhance.run(
        content=b["content"], brand_name=b["brand_name"],
        opportunity=b.get("opportunity") or {}, fanout_queries=b.get("fanout_queries") or [],
        grounding_bundle=b["bundle"], model=b.get("model", FAST)),
        "untapped": enhance.untapped_entities(b["bundle"], b["content"])}


def h_blocks(b: dict) -> dict:
    """Split a draft into publish content + ops pack, and into validatable blocks."""
    publish, pack = docs.split_output(b.get("markdown", ""))
    return {"publish": publish, "ops_pack": pack, "blocks": docs.split_blocks(publish)}


def h_export(b: dict) -> dict:
    """Render the draft to PDF + HTML under out/ and return their paths."""
    out_dir = ROOT / "out"
    out_dir.mkdir(exist_ok=True)
    md = b.get("markdown", "")
    topic = b.get("topic", "Kairos content")
    stem = docs.safe_slug(b.get("filename") or topic) or "kairos-content"
    meta = dict(brand=b.get("brand", ""), topic=topic,
                article_type=b.get("article_type", "Blog Article"),
                language=b.get("language", "English"))

    html_path = out_dir / f"{stem}.html"
    html_path.write_text(
        docs._pdf_html(  # same shell the PDF uses, so both exports look identical
            __import__("markdown2").markdown(
                md, extras=["tables", "fenced-code-blocks", "cuddled-lists", "strike",
                            "header-ids", "break-on-newline"]),
            **meta),
        encoding="utf-8")

    pdf_path = out_dir / f"{stem}.pdf"
    try:
        pdf_path.write_bytes(docs.markdown_to_pdf(md, **meta))
        pdf_ok = True
    except Exception:
        pdf_ok = False

    return {"html_path": str(html_path), "pdf_path": str(pdf_path) if pdf_ok else None,
            "html_url": f"/files/{html_path.name}",
            "pdf_url": f"/files/{pdf_path.name}" if pdf_ok else None}


ROUTES = {
    "/health": h_health, "/clients": h_clients, "/grounding": h_grounding,
    "/topics": h_topics, "/fanout": h_fanout, "/prcalendar": h_prcalendar,
    "/pr_enrich": h_pr_enrich, "/briefqa": h_briefqa, "/crawl": h_crawl,
    "/optplan": h_optplan, "/preferences": h_preferences, "/generate": h_generate,
    "/validate": h_validate, "/enhance": h_enhance, "/export": h_export,
    "/blocks": h_blocks,
}

_FILE_MIME = {".pdf": "application/pdf", ".html": "text/html; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quieter console
        sys.stderr.write("[kairos] %s\n" % (fmt % args))

    def _send_file(self, name: str):
        """Serve a generated export from out/. Name is basenamed — no traversal."""
        safe = os.path.basename(name)
        path = ROOT / "out" / safe
        if not safe or not path.is_file():
            return self._send(404, {"error": "no such export"})
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _FILE_MIME.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'inline; filename="{safe}"')
        self.end_headers()
        self.wfile.write(body)

    def _send(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/files/"):
            return self._send_file(path[len("/files/"):])
        fn = ROUTES.get(path)
        if not fn:
            return self._send(404, {"error": "not found"})
        try:
            self._send(200, fn({}))
        except Exception as e:
            self._send(500, {"error": str(e)})

    def do_POST(self):
        fn = ROUTES.get(self.path.split("?")[0])
        if not fn:
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            return self._send(400, {"error": f"bad JSON: {e}"})
        try:
            self._send(200, fn(body))
        except odin.OdinAuthError as e:
            self._send(401, {"error": str(e), "needs_reauth": True})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"error": str(e)})


if __name__ == "__main__":
    print(f"Kairos service on http://localhost:{PORT} (fast={FAST}, content={CONTENT})")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
