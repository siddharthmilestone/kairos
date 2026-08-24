"""Per-block content validation (runs at generation time).

Splits the publish content into logical blocks and scores each against seven
standards, returning a structured record per block (statuses, holistic score,
CMG nodes + relations) that the UI renders inline behind an info icon.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib import generate
from lib.prompt import render_grounding_context

TEMPLATE = Path(__file__).resolve().parent.parent / "prompts" / "block_validation_prompt.md"
_FENCE = re.compile(r"<<<\s*BLOCKVAL_JSON_START\s*>>>(.*?)<<<\s*BLOCKVAL_JSON_END\s*>>>",
                    re.DOTALL | re.IGNORECASE)
CHECKS = ["grounding", "data", "odin", "intent", "brand_voice", "audience", "semantic"]
CHECK_LABELS = {
    "grounding": "Grounding reasoning", "data": "Data validation", "odin": "Odin validation",
    "intent": "Intent validation", "brand_voice": "Brand-voice validation",
    "audience": "Target-audience validation", "semantic": "Topic-semantic validation",
}


def _build_prompt(*, blocks: list[dict], brand_name: str, brand_voice: str, target_audience: str,
                  opportunity: dict[str, Any], grounding_bundle: dict[str, Any]) -> str:
    t = TEMPLATE.read_text()
    numbered = "\n\n".join(f"### BLOCK {b['index']} — {b['heading']}\n{b['md']}" for b in blocks)
    filled = {
        "{brand_name}": brand_name or "",
        "{topic}": opportunity.get("core_topic", ""),
        "{intent}": opportunity.get("intent", ""),
        "{intent_reasoning}": opportunity.get("intent_reasoning", ""),
        "{primary_keyword}": (opportunity.get("keywords") or [""])[0],
        "{entities}": ", ".join(opportunity.get("entities", []) or []),
        "{target_audience}": target_audience or "(general)",
        "{brand_voice}": (brand_voice or "Professional, warm luxury voice.")[:1200],
        "{grounding_context}": render_grounding_context(grounding_bundle),
        "{blocks}": numbered[:24000],
    }
    for k, v in filled.items():
        t = t.replace(k, str(v))
    return t


def _parse(out: str) -> list[dict]:
    m = _FENCE.search(out)
    raw = m.group(1) if m else out
    candidates = [raw]
    if "{" in raw and "}" in raw:
        candidates.append(raw[raw.index("{"): raw.rindex("}") + 1])
    for c in candidates:
        try:
            data = json.loads(c.strip())
            if isinstance(data, dict) and isinstance(data.get("blocks"), list):
                return data["blocks"]
        except Exception:
            continue
    return []


def run(*, blocks: list[dict], brand_name: str, brand_voice: str, target_audience: str,
        opportunity: dict[str, Any], grounding_bundle: dict[str, Any],
        model: str = "opus") -> list[dict]:
    """Return a list of per-block validation records, index-aligned to `blocks`."""
    if not blocks:
        return []
    prompt_text = _build_prompt(blocks=blocks, brand_name=brand_name, brand_voice=brand_voice,
                                target_audience=target_audience, opportunity=opportunity,
                                grounding_bundle=grounding_bundle)
    # tools off: per-paragraph validation checks against the provided grounding, no web needed → faster.
    recs = _parse(generate.generate(prompt_text, model=model, timeout=700, allow_tools=False))
    by_index = {r.get("index"): r for r in recs if isinstance(r, dict)}
    # align to blocks; fill gaps defensively
    out = []
    for b in blocks:
        r = by_index.get(b["index"]) or {}
        out.append({
            "index": b["index"], "heading": b["heading"],
            "score": r.get("score"),
            "checks": r.get("checks") or {},
            "cmg_nodes": r.get("cmg_nodes") or [],
            "cmg_relations": r.get("cmg_relations") or [],
            "why": r.get("why") or "",
            "sources": r.get("sources") or [],
            "coverage": r.get("coverage") or "",
        })
    return out


def overall_score(records: list[dict]) -> int | None:
    scores = [r.get("score") for r in records if isinstance(r.get("score"), (int, float))]
    return round(sum(scores) / len(scores)) if scores else None
