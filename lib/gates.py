"""Deterministic pre-flight gates on generated content.

These run INSTANTLY (no LLM, no network) the moment a draft lands, so every piece
always ships with a checked, gated artifact even when the user skips the deep
LLM validation. They enforce the mechanical parts of the KAIROS standard: clean
paste-ready prose, real structure, format-appropriate FAQ, depth, readability,
brand-safety (restricted vocabulary), and keyword placement.

Each gate is {id, label, status, detail} where status is "pass" | "warn" | "fail".
`fail` = a hard house-style/brand-safety violation the piece must not ship with.
`warn` = a quality signal worth a look but not a blocker.
"""
from __future__ import annotations

import re

from lib import taxonomy

# Clichés / AI-tells that the WRITING STYLE rules ban outright. Kept in sync with
# prompts/content_generation_prompt.md.
BANNED_PHRASES = [
    "in today's", "in the ever-changing", "in the digital age", "when it comes to",
    "it's important to note", "at the end of the day", "let's dive in", "let's take a look",
    "here's the thing", "in conclusion", "in summary", "to summarize", "unlock",
    "elevate your", "take your", "to the next level", "nestled", "game-changing",
    "game changer", "revolutionary", "seamless", "robust", "cutting-edge", "cutting edge",
    "not only", "whether you're", "world-class", "unforgettable", "moreover,", "furthermore,",
]

_CITATION_TOKEN_RE = re.compile(
    r"\[(?:graph:|web:|author-first-party|not available|to verify|to source|source:)",
    re.IGNORECASE)
_H1_RE = re.compile(r"^\s{0,3}#\s+\S", re.MULTILINE)
_FAQ_RE = re.compile(r"^\s{0,3}##\s+.*frequently asked question", re.IGNORECASE | re.MULTILINE)


def _word_count(md: str) -> int:
    # measure prose only: drop fenced code and table pipes
    txt = re.sub(r"```.*?```", " ", md or "", flags=re.DOTALL)
    txt = re.sub(r"[|#>*_`]", " ", txt)
    return len(re.findall(r"\b[\w'-]+\b", txt))


def _first_n_words(md: str, n: int = 120) -> str:
    txt = re.sub(r"[#>*_`]", " ", md or "")
    return " ".join(re.findall(r"\b[\w'-]+\b", txt)[:n]).lower()


def run_gates(publish_md: str, *, article_type: str,
              restricted_terms: list[str] | None = None,
              primary_keyword: str = "") -> dict:
    """Return {gates:[...], passed, warned, failed, hard_pass:bool, word_count, grade}."""
    md = publish_md or ""
    target = taxonomy.format_target(article_type)
    min_words, ideal_words, _ = target["words"]
    faq_expected = bool(target.get("faq"))
    gates: list[dict] = []

    def add(gid, label, status, detail):
        gates.append({"id": gid, "label": label, "status": status, "detail": detail})

    # 1 — single H1
    h1s = _H1_RE.findall(md)
    add("h1", "Single H1 heading",
        "pass" if len(h1s) == 1 else ("fail" if not h1s else "warn"),
        "One H1" if len(h1s) == 1 else ("No H1 found" if not h1s else f"{len(h1s)} H1s — should be exactly one"))

    # 2 — no citation markup leaked into reader content
    tok = _CITATION_TOKEN_RE.findall(md)
    add("tokens", "No citation markup", "pass" if not tok else "fail",
        "Clean" if not tok else f"{len(tok)} leftover reference token(s) in the copy")

    # 3 — no em/en dashes (house style)
    dash = md.count("—") + md.count("–")
    add("dashes", "No em/en dashes", "pass" if not dash else "fail",
        "None" if not dash else f"{dash} em/en dash(es) — replace with commas/colons")

    # 4 — banned clichés / AI-tells
    low = md.lower()
    hits = sorted({p for p in BANNED_PHRASES if p in low})
    add("cliche", "No banned clichés", "pass" if not hits else "warn",
        "None" if not hits else "Found: " + ", ".join(f'“{h.strip()}”' for h in hits[:6]))

    # 5 — FAQ present when the format expects one
    has_faq = bool(_FAQ_RE.search(md))
    if faq_expected:
        add("faq", "FAQ section present", "pass" if has_faq else "fail",
            "Present" if has_faq else "This format should include a Frequently Asked Questions block")
    else:
        add("faq", "FAQ (not required)", "pass",
            "Not required for this format" + (" — present anyway" if has_faq else ""))

    # 6 — depth / word count
    wc = _word_count(md)
    add("depth", "Content depth",
        "pass" if wc >= min_words else "warn",
        f"{wc} words (target ≥ {min_words}, ideal ~{ideal_words})")

    # 7 — readability
    grade = None
    try:
        from lib import readability
        r = readability.analyze(md)
        grade = r.get("grade")
        add("readability", "Readability",
            "pass" if readability.within_target(md) else "warn",
            f"{r.get('grade_label', 'n/a')} · Flesch ease {r.get('reading_ease')}")
    except Exception:
        add("readability", "Readability", "warn", "Readability could not be computed")

    # 8 — brand-safety restricted vocabulary
    rt = [t.strip() for t in (restricted_terms or []) if t.strip()]
    found_rt = sorted({t for t in rt if re.search(r"\b" + re.escape(t) + r"\b", md, re.IGNORECASE)})
    if rt:
        add("brand_safety", "Brand-safety terms", "pass" if not found_rt else "fail",
            "No restricted terms" if not found_rt else "Contains restricted: " + ", ".join(found_rt))

    # 9 — primary keyword placement (H1 or opening)
    pk = (primary_keyword or "").strip().lower()
    if pk:
        head = ((h1s[0] if h1s else "") + " " + _first_n_words(md)).lower()
        placed = pk in head or all(w in head for w in pk.split()[:4])
        add("keyword", "Primary keyword up top", "pass" if placed else "warn",
            f'“{primary_keyword}” in the H1/opening' if placed else f'“{primary_keyword}” not in the H1 or opening')

    passed = sum(1 for g in gates if g["status"] == "pass")
    warned = sum(1 for g in gates if g["status"] == "warn")
    failed = sum(1 for g in gates if g["status"] == "fail")
    return {"gates": gates, "passed": passed, "warned": warned, "failed": failed,
            "hard_pass": failed == 0, "word_count": wc, "grade": grade}
