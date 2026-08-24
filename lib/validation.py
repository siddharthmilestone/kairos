"""Enterprise Validation Mode — an independent post-generation auditor pass.

Takes the already-generated content plus its grounding and produces four reports
(explainability, KAIROS validation, competitive intelligence, governance &
certification). Runs through claude -p; does NOT regenerate the content.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib import generate
from lib.prompt import render_grounding_context

TEMPLATE = Path(__file__).resolve().parent.parent / "prompts" / "enterprise_validation_prompt.md"

SECTIONS = ["KAIROS_VALIDATION", "COMPETITIVE_INTEL", "GOVERNANCE"]


def build_validation_prompt(*, publish_content: str, brand_name: str, article_type: str,
                            output_language: str, grounding_bundle: dict[str, Any],
                            opportunity: dict[str, Any]) -> str:
    template = TEMPLATE.read_text()
    metadata = {
        "opportunity": opportunity.get("_raw", opportunity),
        "business": {"brand_name": brand_name, "industry": opportunity.get("industry", "")},
    }
    filled = {
        "{brand_name}": brand_name or "",
        "{article_type}": article_type or "Blog Article",
        "{output_language}": output_language or "English",
        "{grounding_context}": render_grounding_context(grounding_bundle),
        "{metadata_json}": json.dumps(metadata, indent=2, ensure_ascii=False),
        "{publish_content}": publish_content or "",
    }
    for k, v in filled.items():
        template = template.replace(k, str(v))
    return template


def run_validation(*, publish_content: str, brand_name: str, article_type: str,
                   output_language: str, grounding_bundle: dict[str, Any],
                   opportunity: dict[str, Any], model: str = "opus") -> str:
    prompt_text = build_validation_prompt(
        publish_content=publish_content, brand_name=brand_name, article_type=article_type,
        output_language=output_language, grounding_bundle=grounding_bundle, opportunity=opportunity)
    return generate.generate(prompt_text, model=model, timeout=900)
