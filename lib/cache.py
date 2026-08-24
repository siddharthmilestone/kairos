"""Persistent, timestamped result cache shared by every generation step.

The POC's slow parts are the AI/Odin generations (topics, brand voices, personas,
fan-out, Q&A, content, optimize plan, PR calendar). For demos these must appear
instantly, so results are cached to disk keyed by their inputs and stamped with a
generation time. The UI shows "Generated <timestamp>" and offers a Regenerate CTA.

A warm-up script (scripts/prewarm.py) pre-populates the business-level caches (topics,
voices, personas) for every Odin client, so a demo never waits on a first run.

One JSON file per (kind, key): {"generated_at": "<ISO>", "data": <payload>}.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "_cache"


def _slug(s: str, maxlen: int = 80) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:maxlen] or "none"


def key(*parts: Any) -> str:
    """Build a stable cache key from its input parts. Long/complex parts are hashed so
    the filename stays bounded, while short readable parts stay legible."""
    raw = "|".join("" if p is None else str(p) for p in parts)
    if len(raw) <= 80 and "\n" not in raw:
        return _slug(raw)
    return _slug(raw[:40]) + "-" + hashlib.sha1(raw.encode()).hexdigest()[:12]


def _path(kind: str, k: str) -> Path:
    d = CACHE_DIR / _slug(kind)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_slug(k, 120)}.json"


def save(kind: str, k: str, data: Any, *, generated_at: str | None = None) -> str:
    """Persist `data` under (kind, key) with a generation timestamp. Returns the ISO stamp."""
    ts = generated_at or _dt.datetime.now().isoformat(timespec="seconds")
    _path(kind, k).write_text(json.dumps({"generated_at": ts, "data": data},
                                         indent=2, ensure_ascii=False))
    return ts


def load(kind: str, k: str) -> tuple[Any, str | None]:
    """Return (data, generated_at_iso) or (None, None) if not cached / unreadable."""
    p = _path(kind, k)
    if not p.exists():
        return None, None
    try:
        obj = json.loads(p.read_text())
        return obj.get("data"), obj.get("generated_at")
    except Exception:  # noqa: BLE001 — a corrupt cache file is a miss, not an error
        return None, None


def clear(kind: str, k: str) -> None:
    try:
        _path(kind, k).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def human_ts(iso: str | None) -> str:
    """'2026-08-19T15:42:03' -> 'Aug 19, 2026 at 3:42 PM'. Empty string on None/parse error."""
    if not iso:
        return ""
    try:
        d = _dt.datetime.fromisoformat(iso)
        hour = d.hour % 12 or 12
        return f"{d:%b} {d.day}, {d.year} at {hour}:{d:%M} {'AM' if d.hour < 12 else 'PM'}"
    except Exception:  # noqa: BLE001
        return iso
