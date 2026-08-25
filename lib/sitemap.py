"""Fetch a site's real internal URLs from its XML sitemap.

Used so internal-link recommendations point at pages that actually exist (finding 9)
instead of invented paths. Best-effort and fully defensive: any failure yields [].
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests

_UA = {"User-Agent": "Mozilla/5.0 (compatible; KairosBot/1.0; +content-intelligence)"}
_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)
_TIMEOUT = 12


def _get(url: str) -> str:
    try:
        r = requests.get(url, headers=_UA, timeout=_TIMEOUT)
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
    return ""


def _base(url: str) -> str:
    if not url:
        return ""
    if not re.match(r"^https?://", url):
        url = "https://" + url
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}" if p.netloc else ""


def _title_from_url(url: str) -> str:
    seg = [s for s in urlparse(url).path.split("/") if s]
    if not seg:
        return "Home"
    return re.sub(r"[-_]+", " ", seg[-1]).strip().title()[:60]


def _sitemap_candidates(base: str) -> list[str]:
    cands = [urljoin(base + "/", "sitemap.xml"), urljoin(base + "/", "sitemap_index.xml")]
    robots = _get(urljoin(base + "/", "robots.txt"))
    for m in re.finditer(r"(?i)sitemap:\s*(\S+)", robots):
        cands.append(m.group(1).strip())
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


def fetch_internal_links(site_url: str, *, max_urls: int = 60) -> list[dict]:
    """Return [{'url','title'}] from the site's sitemap(s). [] on any failure."""
    base = _base(site_url)
    if not base:
        return []
    urls: list[str] = []
    for sm in _sitemap_candidates(base):
        xml = _get(sm)
        if not xml:
            continue
        locs = _LOC_RE.findall(xml)
        # a sitemap index points at child sitemaps (also .xml) — follow one hop
        children = [l for l in locs if l.lower().endswith(".xml")]
        if children and len(children) == len(locs):
            for child in children[:8]:
                urls += _LOC_RE.findall(_get(child))
        else:
            urls += locs
        if len(urls) >= max_urls * 2:
            break
    # de-dupe, keep same-host page URLs, drop assets
    host = urlparse(base).netloc
    seen, out = set(), []
    for u in urls:
        u = u.strip()
        if not u or u in seen:
            continue
        if urlparse(u).netloc and urlparse(u).netloc != host:
            continue
        if re.search(r"\.(xml|jpg|jpeg|png|gif|webp|svg|pdf|css|js|ico)(\?|$)", u, re.I):
            continue
        seen.add(u)
        out.append({"url": u, "title": _title_from_url(u)})
        if len(out) >= max_urls:
            break
    return out
