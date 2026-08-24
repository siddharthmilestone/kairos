"""Auto-match a crawled page to the best-fit Odin content opportunities.

Scores each opportunity by term overlap between the page (title/meta/headings)
and the opportunity's topic + keywords + entities + pillar. Deterministic and
fast — it produces the shortlist the user then picks from in the optimize branch.
"""
from __future__ import annotations

import re
from typing import Any


def _tokens(*texts: str) -> set[str]:
    out: set[str] = set()
    for t in texts:
        out |= set(re.findall(r"[a-z][a-z0-9\-]{2,}", (t or "").lower()))
    return out


def score_opportunity(opp: dict, page_term_set: set[str]) -> tuple[float, list[str]]:
    """Return (0-100 match score, matched terms) for one opportunity vs a page."""
    kw = " ".join(opp.get("keywords") or [])
    ents = " ".join(opp.get("entities") or [])
    opp_terms = _tokens(opp.get("core_topic", ""), kw, ents, opp.get("pillar_topic", ""))
    if not opp_terms:
        return 0.0, []
    overlap = opp_terms & page_term_set
    # Jaccard-ish, weighted toward covering the opportunity's own terms
    coverage = len(overlap) / max(1, len(opp_terms))
    score = round(100 * coverage, 1)
    return score, sorted(overlap)


def match(opportunities: list[dict], page_terms: list[str], top_k: int = 8) -> list[dict]:
    """Rank opportunities by fit to the page. Returns enriched copies with match_score."""
    page_set = set(page_terms)
    ranked = []
    for opp in opportunities:
        s, matched = score_opportunity(opp, page_set)
        ranked.append({**opp, "match_score": s, "matched_terms": matched})
    ranked.sort(key=lambda o: (o["match_score"], o.get("score", 0)), reverse=True)
    return ranked[:top_k]
