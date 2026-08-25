"""Lightweight, append-only observability for content generation runs.

Every generation (topics, fan-out, content, optimize, PR calendar...) can drop a
one-line JSON record here recording what happened: which client/format/model,
how long it took, whether the cache was hit, which quality gates passed or
failed, word count, reading grade, and a rough cost estimate. The log is a plain
JSONL file under data/_runlog/runs.jsonl.

This is best-effort telemetry: appending must never break a generation, so all
IO/serialization errors are swallowed. Reading tolerates partial/corrupt lines.

Pure stdlib, no third-party deps, no network.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

RUNLOG_PATH = Path(__file__).resolve().parent.parent / "data" / "_runlog" / "runs.jsonl"


def append_run(record: dict, *, when: str | None = None) -> None:
    """Append one run record as a JSON line. Never raises.

    Stamps record["ts"] with `when` or the current time (ISO, second precision)
    unless the record already carries a "ts". `record` may be any
    JSON-serializable mapping.
    """
    try:
        rec = dict(record) if record else {}
        if "ts" not in rec:
            rec["ts"] = when or _dt.datetime.now().isoformat(timespec="seconds")
        line = json.dumps(rec, ensure_ascii=False)
        RUNLOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with RUNLOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001 — telemetry must never break a generation
        return


def read_runs(limit: int = 200) -> list[dict]:
    """Return up to `limit` most-recent run records, newest first. [] if missing."""
    try:
        if not RUNLOG_PATH.exists():
            return []
        lines = RUNLOG_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    for line in reversed(lines):
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:  # noqa: BLE001 — skip corrupt lines
            continue
        if isinstance(obj, dict):
            out.append(obj)
        if len(out) >= limit:
            break
    return out


def summary(limit: int = 500) -> dict:
    """Aggregate recent runs into simple counts and rates. Defensive to missing keys."""
    runs = read_runs(limit)
    total = len(runs)
    by_format: dict[str, int] = {}
    by_model: dict[str, int] = {}
    durations: list[float] = []
    cache_hits = 0
    gate_fails = 0
    total_cost = 0.0

    for r in runs:
        fmt = r.get("format")
        if fmt is not None:
            by_format[str(fmt)] = by_format.get(str(fmt), 0) + 1
        model = r.get("model")
        if model is not None:
            by_model[str(model)] = by_model.get(str(model), 0) + 1

        dur = r.get("duration_s")
        if isinstance(dur, (int, float)):
            durations.append(float(dur))

        if r.get("cache_hit"):
            cache_hits += 1

        gf = r.get("gates_failed")
        if isinstance(gf, (list, tuple)):
            if len(gf) > 0:
                gate_fails += 1
        elif isinstance(gf, (int, float)):
            if gf > 0:
                gate_fails += 1
        elif gf:
            gate_fails += 1

        cost = r.get("cost_estimate")
        if isinstance(cost, (int, float)):
            total_cost += float(cost)

    avg_duration = round(sum(durations) / len(durations), 3) if durations else 0.0
    cache_hit_rate = round(cache_hits / total, 3) if total else 0.0
    gate_fail_rate = round(gate_fails / total, 3) if total else 0.0

    return {
        "total": total,
        "by_format": by_format,
        "by_model": by_model,
        "avg_duration_s": avg_duration,
        "cache_hit_rate": cache_hit_rate,
        "gate_fail_rate": gate_fail_rate,
        "total_cost_estimate": round(total_cost, 4),
    }
