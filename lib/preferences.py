"""Grounded brand voices + audience personas for the Preferences step.

Instead of asking the editor to write a brand voice and persona from scratch, we
pre-generate a small set of both — tailored to the ACTUAL business from its Odin
grounding (or, for a non-Odin business, its public profile). The editor picks a
tile (primary flow) or defines their own (secondary flow). The chosen voice +
persona then flow into every generation step so the content adheres to them.
"""
from __future__ import annotations

import json
import re
from typing import Any

from lib import generate
from lib.prompt import render_grounding_context

_FENCE = re.compile(r"<<<\s*PREFS_JSON_START\s*>>>(.*?)<<<\s*PREFS_JSON_END\s*>>>",
                    re.DOTALL | re.IGNORECASE)


def _trim(bundle: dict[str, Any], max_per_type: int = 6, max_ledger: int = 16) -> dict[str, Any]:
    """Compact grounding: voices/personas need brand positioning, review themes, goals and
    amenities — not the full subgraph. Keeps the prompt small so generation is fast."""
    if not bundle or bundle.get("_source") == "llm":
        return bundle
    out: dict[str, Any] = {}
    for k, v in bundle.items():
        if k == "_fact_ledger" and isinstance(v, list):
            out[k] = v[:max_ledger]
        elif k.startswith("_"):
            out[k] = v
        elif isinstance(v, list):
            rows = []
            for r in v[:max_per_type]:
                if isinstance(r, dict):
                    node = {"name": r.get("name", ""), "type": r.get("type", "")}
                    if r.get("facts"):
                        node["facts"] = dict(list(r["facts"].items())[:3])
                    rows.append(node)
                else:
                    rows.append(r)
            out[k] = rows
        else:
            out[k] = v
    return out


def _build_prompt(business_name: str, grounding_bundle: dict[str, Any]) -> str:
    grounding = render_grounding_context(_trim(grounding_bundle))
    return f"""# ROLE
You are a brand strategist and audience researcher for {business_name}. Using ONLY the grounding
below, propose brand voices and guest personas that fit THIS business's real positioning, property
type, guest segments, amenities, and reputation. Never invent facts, awards, or numbers — ground the
choices in the context. Do NOT browse the web.

# GROUNDING CONTEXT (the only source of business truth)
{grounding}

# TASK
Produce EXACTLY 4 distinct BRAND VOICES, EXACTLY 4 distinct GUEST PERSONAS, ONE editorial AUTHOR
profile (for E-E-A-T), and a BRAND-SAFETY block — all grounded in the context.

- **Brand voices** — four different but on-brand tones the brand could genuinely adopt (e.g. refined
  concierge, warm storyteller, authoritative expert, understated luxe — but choose what fits THIS
  brand). For each: a short `name` (2-3 words), a one-line `summary`, and `voice` = 3-5 sentences of
  concrete writing guidance (tone, vocabulary, point of view, sentence rhythm, what to avoid, reading
  level) tailored to this brand. Make the four genuinely different from each other.

- **Guest personas** — four real audience segments this business actually serves (infer them from the
  property type, review themes, business goals, and amenities in the grounding). For each: a short
  `name` (2-3 words), a one-line `summary`, and `persona` = a rich audience description the writer can
  target (who they are, age range, motivations, what they value most, likely objections, decision
  stage, and the tone that resonates with them). Make the four genuinely distinct.

- **Author (E-E-A-T)** — a credible editorial author this brand would publish under. Prefer a real
  team/role identity over a fabricated person (e.g. "{business_name} Editorial Team", "The Concierge
  Desk", a named expert role). Provide `name`, `title` (role), and a 1-2 sentence `bio` establishing
  genuine, grounded expertise (years serving guests, on-property knowledge). Do NOT invent a real
  person's name, credentials, or awards.

- **Brand safety** — `restricted_terms`: 4-10 words/phrases this brand should NOT use in content
  (unsupported superlatives, regulated/overclaiming language, and — if any competitors appear in the
  grounding — competitor brand names). `required_disclaimers`: 0-3 short disclaimers the brand must
  include when relevant (e.g. rate/availability caveats), or an empty list. Ground these; do not invent
  legal claims.

Terse, grounded, no filler.

# OUTPUT — JSON only, between the fences, nothing outside them
<<<PREFS_JSON_START>>>
{{"brand_voices": [
  {{"name": "...", "summary": "one line", "voice": "3-5 sentences of concrete guidance"}}
 ],
 "personas": [
  {{"name": "...", "summary": "one line", "persona": "rich, targetable audience description"}}
 ],
 "author": {{"name": "...", "title": "...", "bio": "1-2 sentences of grounded expertise"}},
 "brand_safety": {{"restricted_terms": ["..."], "required_disclaimers": ["..."]}}
}}
<<<PREFS_JSON_END>>>
"""


def _parse(out: str) -> dict:
    candidates: list[str] = []
    m = _FENCE.search(out)
    if m:
        candidates.append(m.group(1))
    candidates += re.findall(r"```(?:json)?\s*(.*?)```", out, flags=re.DOTALL)
    if "{" in out and "}" in out:
        candidates.append(out[out.index("{"): out.rindex("}") + 1])
    for c in candidates:
        try:
            data = json.loads(c.strip())
            if isinstance(data, dict) and (data.get("brand_voices") or data.get("personas")):
                return data
        except Exception:
            continue
    raise ValueError(f"Could not parse the preferences JSON. Response began: {out[:200]!r}")


def _clean_author(a: Any, business_name: str) -> dict:
    a = a if isinstance(a, dict) else {}
    name = (a.get("name") or "").strip() or f"{business_name} Editorial Team"
    return {"name": name, "title": (a.get("title") or "Editorial Team").strip(),
            "bio": (a.get("bio") or "").strip()}


def _clean_brand_safety(b: Any) -> dict:
    b = b if isinstance(b, dict) else {}
    def _list(x):
        return [s.strip() for s in x if isinstance(s, str) and s.strip()] if isinstance(x, list) else []
    return {"restricted_terms": _list(b.get("restricted_terms"))[:12],
            "required_disclaimers": _list(b.get("required_disclaimers"))[:5]}


def _clean(items: Any, text_key: str) -> list[dict]:
    out = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        name = (it.get("name") or "").strip()
        body = (it.get(text_key) or "").strip()
        if name and body:
            out.append({"name": name, "summary": (it.get("summary") or "").strip(), text_key: body})
    return out


def generate_preferences(*, business_name: str, grounding_bundle: dict[str, Any],
                         model: str = "haiku") -> dict:
    """Return {"brand_voices": [...4], "personas": [...4]}, grounded in the business.
    Raises on parse failure so the caller can fall back to the custom flow."""
    out = generate.generate(_build_prompt(business_name, grounding_bundle),
                            model=model, timeout=180, allow_tools=False)
    data = _parse(out)
    voices = _clean(data.get("brand_voices"), "voice")[:4]
    personas = _clean(data.get("personas"), "persona")[:4]
    if not voices and not personas:
        raise ValueError("No brand voices or personas were generated.")
    return {"brand_voices": voices, "personas": personas,
            "author": _clean_author(data.get("author"), business_name),
            "brand_safety": _clean_brand_safety(data.get("brand_safety"))}
