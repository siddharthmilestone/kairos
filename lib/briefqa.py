"""Grounded, contextual brief questions for the Topic Q&A step.

Turns the approved query fan-out + Odin grounding into first-party elicitation
questions — the specific numbers/names/policies that make content original and
citable. Returns a pool the UI shows a few of, with per-question refresh.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib import generate
from lib.prompt import render_grounding_context

TEMPLATE = Path(__file__).resolve().parent.parent / "prompts" / "brief_questions_prompt.md"
_FENCE = re.compile(r"<<<\s*BRIEFQ_JSON_START\s*>>>(.*?)<<<\s*BRIEFQ_JSON_END\s*>>>",
                    re.DOTALL | re.IGNORECASE)


def build_prompt(*, brand_name: str, seed_topic: str, fanout_queries: list[dict[str, Any]],
                 grounding_bundle: dict[str, Any], n: int = 8) -> str:
    lines = [f"- {q.get('query','')} — need: {q.get('information_need','')}"
             for q in (fanout_queries or [])[:12]]
    filled = {
        "{brand_name}": brand_name or "",
        "{seed_topic}": seed_topic or "",
        "{fanout_list}": "\n".join(lines) or "(none)",
        "{grounding_context}": render_grounding_context(grounding_bundle),
        "{n}": str(n),
    }
    template = TEMPLATE.read_text()
    for k, v in filled.items():
        template = template.replace(k, str(v))
    return template


def _parse(out: str) -> list[str]:
    candidates: list[str] = []
    m = _FENCE.search(out)
    if m:
        candidates.append(m.group(1))
    candidates += re.findall(r"```(?:json)?\s*(.*?)```", out, flags=re.DOTALL)
    if "[" in out and "]" in out:
        candidates.append(out[out.index("["): out.rindex("]") + 1])
    for c in candidates:
        c = c.strip()
        if not c:
            continue
        try:
            data = json.loads(c)
            if isinstance(data, list) and data:
                return [str(x).strip() for x in data if str(x).strip()]
        except Exception:
            continue
    raise ValueError(f"Could not parse brief questions. Response began: {out[:160]!r}")


def run(*, brand_name: str, seed_topic: str, fanout_queries: list[dict[str, Any]],
        grounding_bundle: dict[str, Any], n: int = 8, model: str = "opus") -> list[str]:
    prompt_text = build_prompt(brand_name=brand_name, seed_topic=seed_topic,
                               fanout_queries=fanout_queries, grounding_bundle=grounding_bundle, n=n)
    out = generate.generate(prompt_text, model=model, timeout=300, allow_tools=False)
    qs = _parse(out)
    if not qs:
        raise ValueError("No brief questions returned.")
    # de-dupe preserving order
    seen, uniq = set(), []
    for q in qs:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(q)
    return uniq
