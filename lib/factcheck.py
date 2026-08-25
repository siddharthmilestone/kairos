"""Claim-level fact verification against the grounding — the hallucination hard gate.

The generator self-attests and blockval scores paragraphs, but neither BLOCKS a piece
that asserts a business fact with no source. This pass extracts every checkable factual
claim from the finished content and classifies each against the grounding:

  grounded  — traces to an Odin node / fact ledger atom (or, for non-Odin, a cited public source)
  public    — uncontroversial general/public knowledge, not business-specific
  unverified— a business-specific claim with NO supporting grounding  → gate FAILS

The gate passes only when there are zero `unverified` business claims.
"""
from __future__ import annotations

import json
import re
from typing import Any

from lib import generate
from lib.prompt import is_llm_bundle, render_grounding_context

_FENCE = re.compile(r"<<<\s*FACTCHECK_START\s*>>>(.*?)<<<\s*FACTCHECK_END\s*>>>",
                    re.DOTALL | re.IGNORECASE)


def _build_prompt(publish_content: str, brand_name: str, grounding_bundle: dict[str, Any]) -> str:
    grounding = render_grounding_context(grounding_bundle)
    llm = is_llm_bundle(grounding_bundle)
    source = ("publicly verifiable information cited to a real high-authority source"
              if llm else "the Odin GROUNDING CONTEXT below (the only source of business truth)")
    return f"""# ROLE
You are a meticulous fact-checker for enterprise content. You verify that every business-specific
factual claim in the CONTENT traces to {source}. You do NOT rewrite; you only classify claims.

# GROUNDING CONTEXT (the allowed source of business facts)
{grounding}

# CONTENT TO CHECK (about {brand_name})
```
{publish_content}
```

# TASK
Extract every CHECKABLE FACTUAL CLAIM (a specific, falsifiable statement — a name, number, amenity,
policy, location, award, rating, date, price, capacity, feature). Ignore opinion, generic advice,
marketing framing, and CTAs. For each claim classify `status`:
- "grounded"   — the claim is supported by a specific node/fact in the GROUNDING CONTEXT. Put the
                 supporting node id or fact in `evidence`.
- "public"     — genuinely uncontroversial general knowledge, NOT specific to {brand_name}.
- "unverified" — a {brand_name}-specific claim with NO support in the grounding. This is the
                 dangerous category (possible hallucination). `evidence` = "".

Be strict: if a business-specific number/name/award/policy is not in the grounding, it is "unverified"
even if it sounds plausible. Keep `claim` to the exact assertion (<=160 chars).

# OUTPUT — JSON only between the fences, no prose outside.
<<<FACTCHECK_START>>>
{{"claims": [{{"claim": "...", "status": "grounded|public|unverified", "evidence": "..."}}]}}
<<<FACTCHECK_END>>>
"""


def _parse(out: str) -> list[dict]:
    candidates = []
    m = _FENCE.search(out or "")
    if m:
        candidates.append(m.group(1))
    if "{" in (out or "") and "}" in out:
        candidates.append(out[out.index("{"):out.rindex("}") + 1])
    for c in candidates:
        try:
            data = json.loads(c.strip())
            if isinstance(data, dict) and isinstance(data.get("claims"), list):
                return data["claims"]
        except Exception:
            continue
    return []


def run(*, publish_content: str, brand_name: str, grounding_bundle: dict[str, Any],
        model: str = "haiku", timeout: int = 400) -> dict:
    """Verify claims. Returns {claims, unverified, counts, gate_pass, summary}."""
    if not (publish_content or "").strip():
        return {"claims": [], "unverified": [], "grounded": 0, "public": 0,
                "gate_pass": True, "summary": "No content to check."}
    out = generate.generate(_build_prompt(publish_content, brand_name, grounding_bundle),
                            model=model, timeout=timeout, allow_tools=False)
    claims = _parse(out)
    for c in claims:
        c["status"] = (c.get("status") or "").strip().lower()
        if c["status"] not in ("grounded", "public", "unverified"):
            c["status"] = "unverified"
    unverified = [c for c in claims if c["status"] == "unverified"]
    grounded = sum(1 for c in claims if c["status"] == "grounded")
    public = sum(1 for c in claims if c["status"] == "public")
    gate_pass = len(unverified) == 0
    summary = (f"{grounded} grounded · {public} public knowledge · {len(unverified)} unverified"
               if claims else "No checkable claims extracted.")
    return {"claims": claims, "unverified": unverified, "grounded": grounded,
            "public": public, "gate_pass": gate_pass, "summary": summary}
