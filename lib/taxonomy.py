"""Faceted classification taxonomy for the Choose/Match Topic step.

Four facets group the generated opportunities:
  1. Business Objective  — brand's 8 objectives (hybrid: Odin goals → 8)
  2. Guest Journey       — 10 hospitality touchpoints
  3. Content Gaps        — Structural / Thematic / Critical (existing)
  4. Hotel Features      — per-property amenity/facility taxonomy

Freshly generated topics carry these tags natively; for older library files the
inference helpers below classify them so the grouped UI still works.
"""
from __future__ import annotations

import re

# --- 2 · Guest Journey — the canonical 35-stage hospitality lifecycle (ordered) ---
GUEST_JOURNEY = [
    "Inspiration", "Discovery", "Destination Research", "Property Research",
    "Comparison", "Consideration", "Price Evaluation", "Availability Check",
    "Booking", "Payment", "Confirmation",
    "Pre-Arrival Planning", "Upsell & Upgrade", "Transportation Planning",
    "Arrival", "Check-In", "Orientation", "Room Experience", "Housekeeping",
    "Dining", "Amenities", "Activities & Experiences", "Concierge",
    "Service Requests", "Problem Resolution", "Communication",
    "Check-Out", "Billing", "Feedback", "Review", "Post-Stay Engagement",
    "Loyalty", "Rebooking", "Referral", "Advocacy",
]
_JOURNEY_ORDER = {v: i for i, v in enumerate(GUEST_JOURNEY)}

# The 35 stages roll up into 6 lifecycle phases for a scannable grouped picker.
GUEST_JOURNEY_PHASES = {
    "Dream & Discover": ["Inspiration", "Discovery", "Destination Research", "Property Research"],
    "Evaluate & Compare": ["Comparison", "Consideration", "Price Evaluation", "Availability Check"],
    "Book": ["Booking", "Payment", "Confirmation"],
    "Pre-Arrival": ["Pre-Arrival Planning", "Upsell & Upgrade", "Transportation Planning"],
    "On-Property Stay": ["Arrival", "Check-In", "Orientation", "Room Experience", "Housekeeping",
                         "Dining", "Amenities", "Activities & Experiences", "Concierge",
                         "Service Requests", "Problem Resolution", "Communication"],
    "Departure & Post-Stay": ["Check-Out", "Billing", "Feedback", "Review", "Post-Stay Engagement",
                              "Loyalty", "Rebooking", "Referral", "Advocacy"],
}
_PHASE_ORDER = {p: i for i, p in enumerate(GUEST_JOURNEY_PHASES)}
JOURNEY_PHASE_OF = {stage: phase for phase, stages in GUEST_JOURNEY_PHASES.items() for stage in stages}


def phase_of_journey(stage: str) -> str:
    return JOURNEY_PHASE_OF.get((stage or "").strip(), "Dream & Discover")


# --- 4 · Hotel Features taxonomy ---
HOTEL_FEATURES = [
    "Suites & Accommodations", "Dining & Culinary", "Spa & Wellness", "Pools & Beach",
    "Weddings & Events", "Meetings & MICE", "Family & Kids", "Activities & Excursions",
    "Golf", "All-Inclusive Program", "Fitness & Wellbeing", "Sustainability",
]

# --- 1 · The canonical 10 hospitality business objectives (fixed framework; every
#         topic maps to exactly one). NOT fetched from Odin — Odin informs which are
#         relevant, but the objective vocabulary is this predefined set. ---
DEFAULT_OBJECTIVES = [
    "Increase Revenue & Profitability",
    "Maximize Occupancy & Room Utilization",
    "Increase Direct Bookings & Reduce OTA Dependency",
    "Improve Guest Experience & Satisfaction",
    "Increase Guest Loyalty & Repeat Visits",
    "Optimize Pricing & Revenue Management",
    "Reduce Operating Costs & Improve Efficiency",
    "Increase Ancillary Revenue",
    "Strengthen Brand Awareness & Market Position",
    "Improve Digital Visibility, Demand Generation & Customer Acquisition",
]

# --- Content-value policy (soft steer for topic generation) ---
# High-value archetypes to PRIORITISE — information-gain / first-party-led "quick wins".
PRIORITIZE_ARCHETYPES = [
    "Brand & entity pages",
    "Transaction & task-completion pages",
    "Official documentation, specifications & policies",
    "First-hand tests & performance reviews",
    "Original market, audience & usage research",
    "Live first-party databases & reference hubs",
    "Documented customer outcomes, experiments & case studies",
    "Product-specific implementation & troubleshooting guides",
    "Evidence-led comparisons & selection guides",
    "Personalised tools using live or proprietary data",
    "Curated community & practitioner knowledge",
    "Original reporting & source analysis",
    "Scalable pages powered by unique first-party data with genuine insight",
]
# Low-value archetypes to DEPRIORITISE — commodity / rehashed / programmatic.
DEPRIORITIZE_ARCHETYPES = [
    "Standalone commodity definitions without brand or journey context",
    "Rehashed explainers & how-to guides without original value",
    "Fragmented FAQ / keyword-variant pages serving one intent",
    "Third-party news & press-release rewrites without original input",
    "High-volume tangential topics without a credible business journey",
    "Biased or mass-produced 'best' / comparison / alternatives pages",
    "Generic calculators, quizzes & generators without distinctive inputs",
    "Programmatic pages built from public or competitor data",
]


def content_value_policy() -> str:
    """A soft steer injected into topic generation — favour first-party, information-gain
    content and avoid commodity/rehashed/programmatic pages. Not a hard filter."""
    pri = "\n".join(f"  + {a}" for a in PRIORITIZE_ARCHETYPES)
    dep = "\n".join(f"  - {a}" for a in DEPRIORITIZE_ARCHETYPES)
    return (
        "# CONTENT VALUE POLICY (soft steer — favour first-party, information-gain content)\n"
        "Bias the opportunity set toward these HIGH-VALUE archetypes (quick wins). Tag each\n"
        "opportunity's `content_archetype` with the single closest one (verbatim) and give these a\n"
        "soft score lift so they rank higher:\n"
        f"{pri}\n\n"
        "AVOID / DEPRIORITISE these LOW-VALUE archetypes — do not propose them unless the grounding\n"
        "makes the topic genuinely differentiated with first-party data; apply a soft score penalty:\n"
        f"{dep}\n\n"
        "This is a SOFT steer, not a hard filter — grounding fit and business objective still win, and\n"
        "the mix should stay varied. NEVER fabricate first-party data, tests, research, or outcomes to\n"
        "qualify a topic: if the supporting evidence is not in the Odin graph, choose a different\n"
        "archetype or lower `confidence`.\n"
    )


# =============================================================================
# Decision-criteria taxonomy  (Information-Gain framework, §B)
# Fan-out is reframed from "sub-topics" to "decision criteria a real guest would
# need validated to trust an answer as THE best". Criteria decompose into 6
# categories; two layers sit on top for hospitality: universal (table-stakes) and
# type-specific (weighted by what the property is actually for).
# =============================================================================
CRITERIA_CATEGORIES = [
    "Functional",        # what it actually does / includes, precisely
    "Trust & safety",    # what could go wrong; the honest risk picture
    "Value",             # real cost vs advertised cost; what's hidden
    "Logistics",         # practical friction points (booking, timing, access)
    "Social proof",      # what real guests report, weighted by specificity
    "Emotional / fit",   # who this is genuinely good or bad for, and why
]

# Universal criteria — asked of almost every property regardless of type. These are
# table stakes: missing one is a DISQUALIFIER, not a differentiator.
UNIVERSAL_CRITERIA = [
    "parking", "pet policy", "cancellation terms", "distance from the airport",
    "accessibility", "check-in / check-out flexibility", "wifi reliability",
    "safety & security",
]

HOSPITALITY_TYPES = [
    "Beach / resort", "City", "Business", "Romantic", "Family",
    "Extended-stay", "Luxury / all-inclusive",
]

# Type-specific criteria — weighted differently by what the property is actually for.
TYPE_CRITERIA = {
    "Beach / resort": [
        "what 'beachfront' actually means (swimmable, seaweed-affected, roped-off, walk-in depth)",
        "honest seaweed / sargassum season picture", "lifeguard presence & water safety",
        "real distance from room to sand", "pool crowding & noise at peak hours",
        "reef / snorkelling access and quality",
    ],
    "City": [
        "transit & metro access", "walkability to the reason for the trip",
        "street noise & soundproofing", "neighbourhood safety at night",
        "views vs light-well rooms",
    ],
    "Business": [
        "desk & wifi quality for real work", "meeting / event space specifics",
        "proximity to the venue guests are actually there for", "express / late checkout",
        "quiet floors & business-lounge reality",
    ],
    "Romantic": [
        "adults-only zoning vs genuinely separated", "privacy & noise isolation",
        "view guarantees (not 'view category')", "dining-for-two & turndown specifics",
        "spa couples-treatment availability",
    ],
    "Family": [
        "kids-club real age bands & staff-to-child ratios", "connecting / adjoining room availability",
        "crib & high-chair availability", "pool depth by age & shallow-zone safety",
        "what 'all-inclusive' actually covers for kids (menus, snacks, activities)",
    ],
    "Extended-stay": [
        "kitchen & in-unit laundry specifics", "weekly / monthly rate reality vs nightly",
        "grocery & workspace access nearby", "housekeeping cadence for long stays",
        "long-stay cancellation & extension flexibility",
    ],
    "Luxury / all-inclusive": [
        "what 'all-inclusive' includes vs what is quietly upsold",
        "premium-dining reservation limits & real availability", "service / staff ratios",
        "genuine exclusivity vs peak-week crowding", "what 'luxury' is demonstrated vs asserted",
    ],
}

_TYPE_KW = {
    "Beach / resort": ["beach", "beachfront", "oceanfront", "resort", "sand", "seaside",
                       "island", "coastal", "sargassum", "reef"],
    "City": ["city", "downtown", "urban", "metropolitan", "central"],
    "Business": ["business", "corporate", "conference", "convention", "meetings", "mice"],
    "Romantic": ["romantic", "honeymoon", "couple", "adults-only", "adults only", "elopement"],
    "Family": ["family", "kids", "children", "multigenerational", "family-friendly", "kids club"],
    "Extended-stay": ["extended stay", "extended-stay", "long stay", "serviced apartment",
                      "aparthotel", "residence"],
    "Luxury / all-inclusive": ["all-inclusive", "all inclusive", "luxury", "five-star",
                               "5-star", "ultra-luxury", "villa", "grand velas"],
}


def detect_hospitality_type(text: str) -> str:
    """Best-guess property type from topic/brand/grounding text (a hint the fan-out LLM
    confirms or overrides). Returns '' if nothing matches."""
    t = (text or "").lower()
    best, best_hits = "", 0
    for htype, kws in _TYPE_KW.items():
        hits = sum(1 for k in kws if k in t)
        if hits > best_hits:
            best, best_hits = htype, hits
    return best


def criteria_taxonomy_block(hospitality_type: str = "") -> str:
    """Prompt-ready decision-criteria taxonomy: the 6 categories, the universal
    (table-stakes) criteria, and — when known — the type-specific criteria to weight
    most heavily for this property type."""
    cats = "\n".join(f"  • {c}" for c in CRITERIA_CATEGORIES)
    universal = "; ".join(UNIVERSAL_CRITERIA)
    lines = [
        "# DECISION-CRITERIA TAXONOMY (weight the fan-out by these)",
        "Every decision query decomposes into these 6 criteria categories — tag each query "
        "with the single closest one:",
        cats,
        "",
        f"UNIVERSAL criteria (table stakes — a MISS is a disqualifier, not a differentiator): {universal}.",
    ]
    if hospitality_type and hospitality_type in TYPE_CRITERIA:
        spec = "\n".join(f"  • {c}" for c in TYPE_CRITERIA[hospitality_type])
        lines += [
            "",
            f"TYPE-SPECIFIC criteria for a **{hospitality_type}** property (weight these HEAVIEST — "
            "this is what the property is actually for):",
            spec,
        ]
    else:
        lines += [
            "",
            "First classify this property's hospitality type (one of: "
            + "; ".join(HOSPITALITY_TYPES)
            + "), then weight the type-specific criteria for that type most heavily.",
        ]
    return "\n".join(lines)


# --- 3 · Content gap order ---
GAP_ORDER = {"Critical": 0, "Thematic": 1, "Structural": 2}

FACETS = [
    ("business_objective", "Business Objective"),
    ("guest_journey", "Guest Journey"),
    ("content_gap_type", "Content Gaps"),
    ("hotel_features", "Hotel Features"),
]

# keyword → feature inference (for library topics without native tags)
_FEATURE_KW = {
    "Spa & Wellness": ["spa", "wellness", "hydrotherapy", "massage", "treatment"],
    "Dining & Culinary": ["dining", "restaurant", "culinary", "cuisine", "chef", "michelin", "food", "gastronom"],
    "Weddings & Events": ["wedding", "honeymoon", "elopement", "ceremony", "celebration", "event"],
    "Suites & Accommodations": ["suite", "room", "accommodation", "villa", "penthouse", "oceanfront room"],
    "Pools & Beach": ["pool", "beach", "oceanfront", "beachfront", "swim"],
    "Meetings & MICE": ["meeting", "mice", "conference", "corporate", "incentive", "boardroom", "group"],
    "Family & Kids": ["family", "kids", "children", "teen", "multigenerational", "kids club"],
    "Activities & Excursions": ["excursion", "activity", "activities", "tour", "adventure", "things to do", "diving", "snorkel"],
    "Golf": ["golf"],
    "All-Inclusive Program": ["all-inclusive", "all inclusive", "package", "inclusive"],
    "Fitness & Wellbeing": ["fitness", "gym", "yoga", "wellbeing", "mindfulness"],
    "Sustainability": ["sustainab", "eco", "responsible", "green", "conservation"],
}
# keyword → NEW 35-stage inference (checked in order — specific/earlier stages first).
_JOURNEY_KW = {
    "Comparison": ["vs", "versus", "compare", "comparison", "difference", "which is better", "best resort", "top resort", "alternatives"],
    "Price Evaluation": ["price", "cost", "how much", "deal", "offer", "rate", "value for money", "worth it"],
    "Availability Check": ["availability", "available dates", "sold out", "openings"],
    "Advocacy": ["refer", "referral", "recommend to", "share your"],
    "Loyalty": ["loyalty", "repeat", "rewards", "member", "returning guest"],
    "Review": ["review", "testimonial", "rating", "feedback"],
    "Dining": ["dining", "restaurant", "cuisine", "michelin", "menu", "chef", "culinary"],
    "Activities & Experiences": ["excursion", "activities", "things to do", "adventure", "tour", "experiences", "diving", "snorkel"],
    "Amenities": ["spa", "pool", "amenity", "amenities", "facilities", "gym", "wellness"],
    "Concierge": ["concierge", "butler", "personalized service"],
    "Check-In": ["check-in", "arrival", "airport transfer", "welcome"],
    "Pre-Arrival Planning": ["pre-arrival", "before you go", "packing", "what to pack", "getting there", "plan your trip"],
    "Transportation Planning": ["airport", "transfer", "how to get to", "flights to", "transportation"],
    "Booking": ["book direct", "booking", "reservation", "reserve", "how to book"],
    "Destination Research": ["destination", "things to do in", "guide to", "weather in", "when to visit"],
    "Property Research": ["is it good", "hotel review", "about the resort", "what to expect at"],
    "Inspiration": ["why", "top ", "dream", "inspiration", "discover", "ultimate", "reasons to", "best time to"],
}


def infer_features(text: str) -> list[str]:
    t = (text or "").lower()
    hits = [feat for feat, kws in _FEATURE_KW.items() if any(k in t for k in kws)]
    return hits[:3]


def _match_new(text: str, kw_map: dict, default: str) -> str:
    t = (text or "").lower()
    for value, kws in kw_map.items():
        if any(k in t for k in kws):
            return value
    return default


def map_journey(value: str, intent: str = "", text: str = "") -> str:
    """Map any journey label (old vocabulary or free text) onto one of the 35 stages."""
    v = (value or "").strip()
    if v in _JOURNEY_ORDER:
        return v
    old = {
        "dreaming / inspiration": "Inspiration", "researching / planning": "Destination Research",
        "comparing / evaluating": "Comparison", "booking": "Booking", "pre-arrival": "Pre-Arrival Planning",
        "arrival / check-in": "Check-In", "on-property stay": "Room Experience",
        "dining & experiences": "Dining", "check-out / departure": "Check-Out",
        "post-stay / loyalty": "Loyalty",
    }.get(v.lower())
    if old:
        return old
    hit = _match_new((v + " " + (text or "")), _JOURNEY_KW, "")
    if hit:
        return hit
    return "Booking" if (intent or "").lower() in ("transactional", "commercial") else "Inspiration"


def infer_journey(intent: str, text: str) -> str:
    return map_journey("", intent=intent, text=text)


# keyword → NEW 10-objective inference (for re-tagging libraries / free-text objectives).
_OBJECTIVE_KW = {
    "Increase Revenue & Profitability": ["revenue", "profit", "adr", "revpar", "top line", "margin"],
    "Maximize Occupancy & Room Utilization": ["occupancy", "utilization", "fill rooms", "room nights", "length of stay"],
    "Increase Direct Bookings & Reduce OTA Dependency": ["direct booking", "book direct", "ota", "expedia", "booking.com", "commission"],
    "Improve Guest Experience & Satisfaction": ["experience", "satisfaction", "reputation", "reviews", "service quality", "nps"],
    "Increase Guest Loyalty & Repeat Visits": ["loyalty", "repeat", "retention", "member", "returning"],
    "Optimize Pricing & Revenue Management": ["pricing", "rate", "yield", "revenue management", "dynamic pricing"],
    "Reduce Operating Costs & Improve Efficiency": ["cost", "efficiency", "operations", "labor", "energy", "automation"],
    "Increase Ancillary Revenue": ["ancillary", "upsell", "spa", "dining", "wedding", "event", "package", "add-on", "f&b"],
    "Strengthen Brand Awareness & Market Position": ["brand", "awareness", "authority", "positioning", "market position", "pr"],
    "Improve Digital Visibility, Demand Generation & Customer Acquisition": ["visibility", "seo", "geo", "aio", "demand", "acquisition", "digital", "traffic", "search", "leads"],
}


def map_objective(value: str, text: str = "") -> str:
    """Map any objective label (old vocabulary or free text) onto one of the 10 objectives."""
    v = (value or "").strip()
    if v in DEFAULT_OBJECTIVES:
        return v
    return _match_new((v + " " + (text or "")), _OBJECTIVE_KW,
                      "Strengthen Brand Awareness & Market Position")


_INTENT_REASONING = {
    "commercial": "Commercial intent — the query weighs options and shows buying consideration; "
                  "the content should compare, prove value with grounded facts, and guide the decision.",
    "transactional": "Transactional intent — the query signals readiness to act or book; the content "
                     "should remove friction and drive the conversion with a clear next step.",
    "informational": "Informational intent — the query seeks to learn; the content should answer the "
                     "question thoroughly and completely to earn topical authority and citations.",
    "navigational": "Navigational intent — the query targets a specific brand or page; the content "
                    "should decisively own that branded query.",
    "local": "Local intent — the query is place-specific; the content should surface location facts, "
             "proximity, and local relevance.",
}


def infer_intent_reasoning(intent: str) -> str:
    return _INTENT_REASONING.get((intent or "").strip().lower(),
                                 "Intent classified from the query type, keywords, and journey stage.")


def group_topics(records: list[dict], facet_key: str) -> list[tuple[str, list[dict]]]:
    """Return ordered [(category_value, [records])] for a facet.

    hotel_features is list-valued (a topic appears under each of its features);
    the other facets are scalar. Guest journey groups by the 6 LIFECYCLE PHASES
    (each topic keeps its precise 35-stage tag on its card). Empty → 'Unclassified'.
    """
    buckets: dict[str, list[dict]] = {}
    for r in records:
        if facet_key == "guest_journey":
            stage = (r.get("guest_journey") or "").strip()
            vals = [phase_of_journey(stage)] if stage else ["Unclassified"]
        else:
            val = r.get(facet_key)
            vals = val if isinstance(val, list) else [val]
            vals = [v for v in vals if v] or ["Unclassified"]
        for v in vals:
            buckets.setdefault(str(v), []).append(r)

    def sort_key(item):
        name, recs = item
        if name == "Unclassified":
            return (9, 0, name)
        if facet_key == "guest_journey":                 # order by lifecycle phase
            return (0, _PHASE_ORDER.get(name, 50), name)
        if facet_key == "content_gap_type":
            return (0, GAP_ORDER.get(name, 5), name)
        return (0, -len(recs), name)  # objective & features: by count desc

    # within each guest-journey phase, order topics by their precise stage
    if facet_key == "guest_journey":
        for name in buckets:
            buckets[name].sort(key=lambda r: _JOURNEY_ORDER.get((r.get("guest_journey") or "").strip(), 99))
    return sorted(buckets.items(), key=sort_key)
