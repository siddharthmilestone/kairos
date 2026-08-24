"""Content Enhancement Advisor — proposes clickable "Apply / Dismiss" upgrades.

Runs at generation time (concurrently with validation) against the finished draft.
Returns a ranked list of concrete, grounded enhancements the editor can apply; an
applied set is fed back into the next generation pass.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib import generate
from lib.prompt import render_grounding_context

TEMPLATE = Path(__file__).resolve().parent.parent / "prompts" / "enhancement_prompt.md"
APPLY_TEMPLATE = Path(__file__).resolve().parent.parent / "prompts" / "apply_enhancement_prompt.md"
_FENCE = re.compile(r"<<<\s*ENHANCE_JSON_START\s*>>>(.*?)<<<\s*ENHANCE_JSON_END\s*>>>",
                    re.DOTALL | re.IGNORECASE)
_REVISED = re.compile(r"<<<\s*REVISED_START\s*>>>(.*?)<<<\s*REVISED_END\s*>>>",
                      re.DOTALL | re.IGNORECASE)
_IMPACT_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_prompt(*, content: str, brand_name: str, opportunity: dict[str, Any],
                 fanout_queries: list[dict[str, Any]], grounding_bundle: dict[str, Any]) -> str:
    fo = "\n".join(f"- {q.get('query','')}" for q in (fanout_queries or [])[:14]) or "(none)"
    filled = {
        "{brand_name}": brand_name or "",
        "{topic}": opportunity.get("core_topic", ""),
        "{intent}": opportunity.get("intent", ""),
        "{primary_keyword}": (opportunity.get("keywords") or [""])[0],
        "{fanout_list}": fo,
        "{grounding_context}": render_grounding_context(grounding_bundle),
        "{content}": (content or "")[:16000],
    }
    template = TEMPLATE.read_text()
    for k, v in filled.items():
        template = template.replace(k, str(v))
    return template


def _parse(out: str) -> list[dict]:
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
            if isinstance(data, dict) and isinstance(data.get("suggestions"), list):
                return data["suggestions"]
            if isinstance(data, list):
                return data
        except Exception:
            continue
    return []


def run(*, content: str, brand_name: str, opportunity: dict[str, Any],
        fanout_queries: list[dict[str, Any]], grounding_bundle: dict[str, Any],
        model: str = "opus") -> list[dict]:
    prompt_text = build_prompt(content=content, brand_name=brand_name, opportunity=opportunity,
                               fanout_queries=fanout_queries, grounding_bundle=grounding_bundle)
    recs = _parse(generate.generate(prompt_text, model=model, timeout=500, allow_tools=False))
    out = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict) or not r.get("title"):
            continue
        r["id"] = r.get("id") or f"enh{i+1:02d}"
        r["impact"] = (r.get("impact") or "Medium").title()
        out.append(r)
    out.sort(key=lambda r: _IMPACT_ORDER.get(r["impact"].lower(), 1))
    return out


def apply_one(*, content: str, suggestion: dict[str, Any], brand_name: str,
              grounding_bundle: dict[str, Any], model: str = "opus") -> str:
    """Surgically revise `content` to incorporate one enhancement. Returns the full
    revised content, or the original unchanged if the edit couldn't be parsed."""
    filled = {
        "{title}": suggestion.get("title", ""),
        "{insert}": suggestion.get("insert") or suggestion.get("impact_note") or "",
        "{why}": suggestion.get("why", ""),
        "{grounding_context}": render_grounding_context(grounding_bundle),
        "{content}": content or "",
    }
    template = APPLY_TEMPLATE.read_text()
    for k, v in filled.items():
        template = template.replace(k, str(v))
    out = generate.generate(template, model=model, timeout=500, allow_tools=False)
    m = _REVISED.search(out)
    revised = (m.group(1) if m else out).strip()
    return revised or content


def untapped_entities(grounding_bundle: dict[str, Any], content: str, limit: int = 12) -> list[str]:
    """Graph entities not yet referenced in the content (client-side, no model call)."""
    text = (content or "").lower()
    seen, out = set(), []
    for etype, rows in (grounding_bundle or {}).items():
        if etype.startswith("_") or not isinstance(rows, list):
            continue
        for r in rows:
            name = (r.get("name") or "").strip() if isinstance(r, dict) else ""
            if not name or len(name) < 3:
                continue
            k = name.lower()
            if k in seen or k in text:
                continue
            seen.add(k)
            out.append(name)
    return out[:limit]
