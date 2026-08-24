"""Real SERP integration for the Query Fan-Out step.

Provider-agnostic: auto-detects Serper.dev (SERPER_API_KEY) or SerpApi
(SERPAPI_API_KEY) from the environment — no key is ever handled in code, and no
extra pip dependency (stdlib urllib). When no key is set, this is disabled and
the fan-out falls back to the model's best-effort SERP estimate.

Given a fan-out, it fetches live Google organic results per query, then sets the
real `top_competitor` (top organic result not on the client's domain) and a real
`serp_estimate` (the client's own rank when the client domain is known).
"""
from __future__ import annotations

import concurrent.futures as _cf
import json
import os
import urllib.parse
import urllib.request
from typing import Any
from urllib.parse import urlparse

_CACHE: dict[str, list[dict]] = {}


def _provider() -> str | None:
    if os.environ.get("SERPER_API_KEY"):
        return "serper"
    if os.environ.get("SERPAPI_API_KEY") or os.environ.get("SERPAPI_KEY"):
        return "serpapi"
    return None


def enabled() -> bool:
    return _provider() is not None


def status() -> dict[str, Any]:
    return {"enabled": enabled(), "provider": _provider()}


def domain_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").replace("www.", "").lower()
    except Exception:
        return ""


def search(query: str, num: int = 10, gl: str = "us", hl: str = "en", timeout: int = 15) -> list[dict]:
    """Return [{position, title, url, domain}] organic results, or [] on failure/disabled."""
    query = (query or "").strip()
    if not query or not enabled():
        return []
    if query in _CACHE:
        return _CACHE[query]
    p = _provider()
    out: list[dict] = []
    try:
        if p == "serper":
            body = json.dumps({"q": query, "num": num, "gl": gl, "hl": hl}).encode()
            req = urllib.request.Request(
                "https://google.serper.dev/search", data=body,
                headers={"X-API-KEY": os.environ["SERPER_API_KEY"], "Content-Type": "application/json"})
            data = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())  # noqa: S310
            org = data.get("organic", []) or []
        else:  # serpapi
            key = os.environ.get("SERPAPI_API_KEY") or os.environ.get("SERPAPI_KEY")
            qs = urllib.parse.urlencode({"engine": "google", "q": query, "num": num,
                                         "gl": gl, "hl": hl, "api_key": key})
            data = json.loads(urllib.request.urlopen(  # noqa: S310
                f"https://serpapi.com/search.json?{qs}", timeout=timeout).read().decode())
            org = data.get("organic_results", []) or []
        for i, o in enumerate(org[:num]):
            link = o.get("link") or o.get("url") or ""
            out.append({"position": o.get("position", i + 1), "title": o.get("title", ""),
                        "url": link, "domain": domain_of(link)})
    except Exception:
        out = []
    _CACHE[query] = out
    return out


def enrich_query(q: dict, client_domain: str | None = None, num: int = 10) -> dict:
    """Overlay real SERP data onto one fan-out query dict (in place)."""
    results = search(q.get("query", ""), num=num)
    if not results:
        return q
    q["serp_results"] = results[:5]
    q["serp_source"] = _provider()
    cd = (client_domain or "").replace("www.", "").lower()
    our_pos = None
    if cd:
        for r in results:
            if cd and (cd in r["domain"] or r["domain"] in cd):
                our_pos = r["position"]
                break
    comp = next((r for r in results if not (cd and (cd in r["domain"] or r["domain"] in cd))), None)
    if comp:
        q["top_competitor"] = {"name": comp["domain"], "url": comp["url"], "position": comp["position"]}
    if our_pos is not None:
        q["serp_estimate"] = f"you rank #{our_pos}"
    elif cd:
        q["serp_estimate"] = f"not in top {num}"
    elif comp:
        q["serp_estimate"] = f"top result #{comp['position']}"
    return q


def enrich_fanout(data: dict, client_domain: str | None = None, max_queries: int = 14) -> dict:
    """Enrich the highest-importance queries with live SERP data (parallel). No-op if disabled."""
    if not enabled():
        return data
    queries = sorted(data.get("queries", []), key=lambda q: q.get("importance", 0), reverse=True)
    targets = queries[:max_queries]
    with _cf.ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(lambda q: enrich_query(q, client_domain=client_domain), targets))
    data.setdefault("summary", {})["serp_source"] = _provider()
    return data
