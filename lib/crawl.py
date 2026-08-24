"""Crawl a page for the Optimize branch.

Prefers a headless-browser render (Playwright) so JS-heavy hotel pages are
captured; falls back to a plain HTTP fetch. Extracts title, meta, headings,
main text, and JSON-LD schema.org markup — enough to auto-match the page to
Odin content opportunities. (The deep KAIROS audit re-fetches with full
rendering via claude's own tools.)
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ContentStudioPOC/1.0"


def _http_get(url: str, timeout: int = 25) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 (user-supplied URL is intentional)
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def _render_html(url: str, timeout: int = 20000) -> tuple[str, str]:
    """Return (html, method). Try Playwright; fall back to HTTP.

    Speed-tuned: waits for `domcontentloaded` (not `networkidle`, which can stall on
    ad/analytics-heavy pages), and blocks images/media/fonts/CSS — we extract text and
    JSON-LD, never render visuals, so skipping those assets cuts crawl time a lot."""
    try:
        from playwright.sync_api import sync_playwright

        _skip = {"image", "media", "font", "stylesheet"}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA)
            try:
                page.route("**/*", lambda r: (r.abort() if r.request.resource_type in _skip
                                              else r.continue_()))
            except Exception:
                pass
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            # brief scroll to trigger lazy/below-the-fold content (bounded for speed)
            try:
                prev = 0
                for _ in range(8):
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(200)
                    height = page.evaluate("document.body.scrollHeight")
                    if height == prev:
                        break
                    prev = height
                page.wait_for_timeout(300)
            except Exception:
                pass
            html = page.content()
            browser.close()
            return html, "headless-browser"
    except Exception:
        return _http_get(url), "http-fetch"


def _extract_jsonld(soup) -> list[dict]:
    blocks: list[dict] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        try:
            data = json.loads(raw)
        except Exception:
            continue
        blocks.extend(data if isinstance(data, list) else [data])
    return blocks


def _schema_types(jsonld: list[dict]) -> list[str]:
    types: list[str] = []
    for b in jsonld:
        t = b.get("@type") if isinstance(b, dict) else None
        if isinstance(t, list):
            types.extend(t)
        elif t:
            types.append(t)
    # dedupe, preserve order
    seen, out = set(), []
    for t in types:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def crawl(url: str) -> dict[str, Any]:
    """Return a structured snapshot of the page."""
    from bs4 import BeautifulSoup

    if not re.match(r"^https?://", url):
        url = "https://" + url
    html, method = _render_html(url)
    soup = BeautifulSoup(html, "lxml")

    for bad in soup(["script", "style", "noscript", "template"]):
        bad.decompose()

    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    meta_desc = ""
    md = soup.find("meta", attrs={"name": "description"})
    if md and md.get("content"):
        meta_desc = md["content"].strip()

    # --- strip only true chrome: structural tags + cookie/consent banners ---
    for bad in soup(["nav", "header", "footer", "aside", "form", "button",
                     "iframe", "svg"]):
        bad.decompose()
    for el in soup.select('[class*="cookie" i], [id*="cookie" i], '
                          '[class*="consent" i], [id*="consent" i]'):
        el.decompose()

    # content region = <main>/<article> when present (avoids nav/footer), else body
    content_root = soup.find("main") or soup.find("article") or soup.body or soup
    headings = {"h1": [], "h2": [], "h3": []}
    for level in headings:
        for h in content_root.find_all(level):
            txt = h.get_text(" ", strip=True)
            if txt:
                headings[level].append(txt)

    # Gather candidates and keep the fullest real-content version.
    candidates: list[tuple[str, str]] = []
    dom_main = re.sub(r"\n{3,}", "\n\n", content_root.get_text("\n", strip=True))
    if dom_main.split():
        candidates.append((dom_main, f"{method}+main-region"))
    try:
        import trafilatura
        extracted = trafilatura.extract(
            html, include_comments=False, include_tables=True,
            favor_recall=True, include_formatting=False, url=url)
        if extracted:
            candidates.append((extracted.strip(), f"{method}+trafilatura"))
    except Exception:
        pass
    if not candidates:
        candidates = [(re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True)), method)]
    body_text, method = max(candidates, key=lambda c: len(c[0].split()))

    jsonld = _extract_jsonld(BeautifulSoup(html, "lxml"))

    return {
        "url": url,
        "fetch_method": method,
        "title": title,
        "meta_description": meta_desc,
        "headings": headings,
        "word_count": len(body_text.split()),
        "body_text": body_text,          # full page copy — no cap
        "schema_types": _schema_types(jsonld),
        "jsonld": jsonld[:10],
    }


_STOP = {"the", "and", "for", "with", "your", "our", "you", "are", "from", "this", "that",
         "has", "have", "all", "can", "will", "more", "was", "how", "what", "who", "why",
         "where", "when", "into", "not", "but", "his", "her", "its", "also", "their", "they",
         "them", "which", "been", "were", "would", "could", "about", "over", "than", "then",
         "these", "those", "here", "there", "such", "each", "any", "one", "two", "get", "out"}


def page_terms(snapshot: dict[str, Any], include_body: bool = True,
               body_top: int = 60) -> list[str]:
    """Significant terms from a crawl snapshot, weighted for opportunity matching.

    Title/meta/headings are always included (high signal). Body copy contributes
    its most frequent content words so matching reflects what the page is *about*.
    """
    strong = [snapshot.get("title", ""), snapshot.get("meta_description", "")]
    strong += snapshot.get("headings", {}).get("h1", [])
    strong += snapshot.get("headings", {}).get("h2", [])
    strong += snapshot.get("headings", {}).get("h3", [])
    terms = [w for w in re.findall(r"[a-z][a-z0-9\-]{2,}", " ".join(strong).lower())
             if w not in _STOP]

    if include_body:
        body_words = [w for w in re.findall(r"[a-z][a-z0-9\-]{3,}",
                                            (snapshot.get("body_text", "") or "").lower())
                      if w not in _STOP]
        freq: dict[str, int] = {}
        for w in body_words:
            freq[w] = freq.get(w, 0) + 1
        top = sorted(freq, key=lambda w: freq[w], reverse=True)[:body_top]
        terms += top
    return terms
