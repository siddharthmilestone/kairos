"""Model calls over the Anthropic API instead of the `claude` CLI.

`lib/generate.py` shells out to `claude -p`, which needs the binary and the user's
OAuth session — neither exists in a deployment. This is a drop-in replacement with
the same signature, so every prompt, parser and workflow step is untouched.

Select it with KAIROS_MODEL_BACKEND=api (see lib/generate.py).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

# The CLI takes short names; the API needs full ids.
MODELS = {
    "opus": os.environ.get("KAIROS_MODEL_OPUS", "claude-opus-5"),
    "sonnet": os.environ.get("KAIROS_MODEL_SONNET", "claude-sonnet-5"),
    "haiku": os.environ.get("KAIROS_MODEL_HAIKU", "claude-haiku-4-5-20251001"),
}

# A full draft plus its ops pack and score report runs long; structured steps do not.
MAX_TOKENS = int(os.environ.get("KAIROS_MAX_TOKENS", "16000"))


def _key() -> str:
    k = os.environ.get("ANTHROPIC_API_KEY", "")
    if not k:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Kairos needs it to generate content."
        )
    return k


def generate(prompt: str, model: str = "opus", timeout: int = 900,
             allow_tools: bool = True) -> str:
    """Same contract as generate.generate(): prompt in, text out.

    `allow_tools` is accepted for signature compatibility but ignored — the hosted
    build never browses the web. Every step is already grounded in the knowledge
    base, and live browsing is what made these calls unbounded in the first place.
    """
    body = {
        "model": MODELS.get(model, model),
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": _key(),
            "anthropic-version": API_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Anthropic API {e.code}: {e.read().decode()[:400]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach the Anthropic API: {e.reason}") from e

    text = "".join(
        block.get("text", "") for block in data.get("content", [])
        if block.get("type") == "text"
    ).strip()
    if not text:
        raise RuntimeError(f"Empty response (stop_reason={data.get('stop_reason')})")
    return text
