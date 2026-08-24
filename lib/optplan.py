"""Pre-generation Optimization Plan (Optimize flow).

After the crawl and topic match, analyse the existing page against the target
opportunity, Odin grounding, and the live competitor landscape, and produce a
Retain / Enhance / Prune / Create plan the user reviews before generation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lib import generate
from lib.prompt import render_grounding_context

TEMPLATE = Path(__file__).resolve().parent.parent / "prompts" / "optimization_plan_prompt.md"
BUCKETS = ["RETAIN", "ENHANCE", "PRUNE", "CREATE", "PLAN_SUMMARY"]


def build_plan_prompt(*, brand_name: str, article_type: str, opportunity: dict[str, Any],
                      crawl_snapshot: dict[str, Any], grounding_bundle: dict[str, Any]) -> str:
    t = TEMPLATE.read_text()
    h = crawl_snapshot.get("headings", {})
    headings = " | ".join((h.get("h1", []) + h.get("h2", []))[:20])
    filled = {
        "{brand_name}": brand_name or "",
        "{article_type}": article_type or "Web Page",
        "{topic}": opportunity.get("core_topic", ""),
        "{intent}": opportunity.get("intent", ""),
        "{intent_reasoning}": opportunity.get("intent_reasoning", ""),
        "{primary_keyword}": (opportunity.get("keywords") or [""])[0],
        "{entities}": ", ".join(opportunity.get("entities", []) or []),
        "{content_gap_type}": opportunity.get("content_gap_type", ""),
        "{url}": crawl_snapshot.get("url", ""),
        "{title}": crawl_snapshot.get("title", ""),
        "{meta}": crawl_snapshot.get("meta_description", ""),
        "{schema_types}": ", ".join(crawl_snapshot.get("schema_types", [])) or "none",
        "{headings}": headings,
        "{body_text}": (crawl_snapshot.get("body_text", "") or "")[:40000],
        "{grounding_context}": render_grounding_context(grounding_bundle),
    }
    for k, v in filled.items():
        t = t.replace(k, str(v))
    return t


def run_plan(*, brand_name: str, article_type: str, opportunity: dict[str, Any],
             crawl_snapshot: dict[str, Any], grounding_bundle: dict[str, Any],
             model: str = "opus") -> str:
    prompt_text = build_plan_prompt(
        brand_name=brand_name, article_type=article_type, opportunity=opportunity,
        crawl_snapshot=crawl_snapshot, grounding_bundle=grounding_bundle)
    return generate.generate(prompt_text, model=model, timeout=700)
