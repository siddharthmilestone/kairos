"""Load & normalize content-opportunity JSON files.

Supports the canonical geo-content-opportunity-engine schema (snake_case) and
the Title-Case presentation variant (the Reef file). Returns a uniform internal
record so the UI and prompt builder don't care which file they got.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib import taxonomy

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _first(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] not in (None, "", [], {}):
            return d[k]
    return default


def _norm_one(o: dict, idx: int) -> dict[str, Any]:
    """Map either schema variant onto a uniform record."""
    keywords = _first(o, "keywords", "Keywords", "target_keywords", default=[]) or []
    prompts = _first(o, "prompts", "Prompts", default=[]) or []
    mgn = _first(o, "memory_graph_nodes", "Memory Graph Nodes", default={}) or {}
    entities = []
    if isinstance(mgn, dict):
        for ent in mgn.get("entities", []):
            entities.append(ent.get("label") if isinstance(ent, dict) else ent)
    entities = [e for e in entities if e]
    rec = {
        "id": _first(o, "id", default=f"opp-{idx:03d}"),
        "core_topic": _first(o, "core_topic", "Core Topic", "title", default="(untitled)"),
        "industry": _first(o, "industry", "Industry", default=""),
        "pillar_topic": _first(o, "pillar_topic", "Pillar Topic", "page_type", default="General"),
        "keywords": keywords,
        "prompts": prompts,
        "intent": _first(o, "intent", "Intent", default="Informational"),
        "intent_reasoning": _first(o, "intent_reasoning", "Intent Reasoning", default=""),
        "reach": _first(o, "reach", "Reach", default="Unknown"),
        "geo_lift": _first(o, "geo_lift", "GEO Lift", default="Unknown"),
        "effort": _first(o, "effort", "Effort", default=""),
        "location_city": _first(o, "location_city", "Location City", default=""),
        "location_country": _first(o, "location_country", "Location Country", default=""),
        "memory_graph_nodes": mgn,
        "entities": entities,
        "business_objective": _first(o, "business_objective", "Business Objective", "objective", default=""),
        "content_archetype": _first(o, "content_archetype", "Content Archetype", default=""),
        "customer_journey": _first(o, "customer_journey", "Customer Journey", "journey_stage", default=""),
        "content_gap_type": _first(o, "content_gap_type", "Content Gap Type", "gap_type", default=""),
        "guest_journey": _first(o, "guest_journey", "Guest Journey", default=""),
        "hotel_features": _first(o, "hotel_features", "Hotel Features", default=[]),
        "recommendation": _first(o, "recommendation", "Recommendation", "content_type", default=""),
        "confidence": _first(o, "confidence", "Confidence", default=""),
        "geo_signals": _first(o, "geo_signals", "GEO Signals", default={}),
        "evidence_sources": _first(o, "evidence_sources", "Evidence Sources", "why_evidence_chain", default=[]),
        "score": _first(o, "score", "opportunity_score", default=0),
        "_raw": o,
    }
    # normalize hotel_features to a list
    if isinstance(rec["hotel_features"], str):
        rec["hotel_features"] = [rec["hotel_features"]] if rec["hotel_features"] else []
    # fallback classification for library topics that lack native facet tags
    text = " ".join([rec["core_topic"], rec["pillar_topic"], " ".join(rec["keywords"]),
                     " ".join(rec["entities"])])
    if not rec["hotel_features"]:
        rec["hotel_features"] = taxonomy.infer_features(text)
    # Coerce onto the canonical vocabularies (10 objectives · 35 journey stages) — this maps
    # both freshly-generated and legacy/library values onto the fixed frameworks so every
    # topic nests correctly regardless of source.
    rec["guest_journey"] = taxonomy.map_journey(rec["guest_journey"], intent=rec["intent"], text=text)
    rec["business_objective"] = taxonomy.map_objective(rec["business_objective"], text=text)
    if not rec["intent_reasoning"]:
        rec["intent_reasoning"] = taxonomy.infer_intent_reasoning(rec["intent"])
    return rec


def load_file(path: str | Path) -> tuple[dict, list[dict]]:
    """Return (meta, [normalized opportunity records])."""
    data = json.loads(Path(path).read_text())
    meta = {}
    if isinstance(data, dict):
        meta = data.get("_meta") or data.get("meta") or {}
        raw = data.get("opportunities")
        if raw is None:  # legacy create/optimize shape
            raw = (data.get("create", []) or []) + (data.get("optimize", []) or [])
    else:
        raw = data
    records = [_norm_one(o, i) for i, o in enumerate(raw)]
    return meta, records


def normalize(data: dict | list) -> list[dict]:
    """Normalize an already-parsed opportunities payload into uniform records."""
    if isinstance(data, dict):
        raw = data.get("opportunities")
        if raw is None:
            raw = (data.get("create", []) or []) + (data.get("optimize", []) or [])
    else:
        raw = data
    return [_norm_one(o, i) for i, o in enumerate(raw or [])]


def list_data_files() -> list[Path]:
    if not DATA_DIR.exists():
        return []
    return sorted(DATA_DIR.glob("*.json"))
