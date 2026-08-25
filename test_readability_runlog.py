"""Tests for lib/readability.py and lib/runlog.py. Plain asserts; prints OK."""
from __future__ import annotations

import tempfile
from pathlib import Path

from lib import readability, runlog


def test_analyze_basic():
    m = readability.analyze("The cat sat on the mat. It was a warm day.")
    assert m["words"] > 0, m
    assert m["sentences"] >= 1, m
    assert isinstance(m["grade"], float), m
    assert isinstance(m["grade_label"], str) and m["grade_label"], m
    assert isinstance(m["reading_ease"], float), m


def test_analyze_empty():
    m = readability.analyze("")
    assert m["words"] == 0
    assert m["sentences"] == 0
    assert m["syllables"] == 0
    assert m["reading_ease"] == 0.0
    assert m["grade"] == 0.0
    assert m["grade_label"] == "n/a"
    assert m["avg_sentence_len"] == 0.0


def test_within_target_and_complexity():
    simple = "The dog ran. The cat sat. We had fun."
    assert readability.within_target(simple) is True

    convoluted = (
        "Notwithstanding the aforementioned considerations, the multifaceted "
        "organizational restructuring initiative, which encompassed numerous "
        "interdependent stakeholder communications, procedural modifications, and "
        "administrative reconfigurations, necessitated comprehensive deliberation "
        "throughout the extended implementation timeline."
    )
    g_simple = readability.analyze(simple)["grade"]
    g_hard = readability.analyze(convoluted)["grade"]
    assert g_hard > g_simple, (g_hard, g_simple)


def test_code_and_tables_excluded():
    prose = (
        "Here is a short guide to the setup. It should be easy to follow. "
        "Read each step and try it."
    )
    with_code = (
        prose
        + "\n\n```python\n"
        + "def f(x):\n    return x * x * x + 42 / 7 - 1\n"
        + "```\n\n"
        + "| Col A | Col B |\n| --- | --- |\n| 1 | 2 |\n"
    )
    a = readability.analyze(prose)
    b = readability.analyze(with_code)
    assert a["words"] == b["words"], (a, b)
    assert abs(a["grade"] - b["grade"]) < 0.05, (a["grade"], b["grade"])


def test_runlog_roundtrip():
    orig = runlog.RUNLOG_PATH
    tmpdir = tempfile.mkdtemp()
    tmp_path = Path(tmpdir) / "runs.jsonl"
    runlog.RUNLOG_PATH = tmp_path
    try:
        runlog.append_run({
            "client": "acme", "format": "blog", "model": "opus",
            "duration_s": 2.0, "cache_hit": False,
            "gates_failed": ["readability"], "cost_estimate": 0.10,
        }, when="2026-08-25T10:00:00")
        runlog.append_run({
            "client": "acme", "format": "social", "model": "haiku",
            "duration_s": 4.0, "cache_hit": True,
            "gates_failed": [], "cost_estimate": 0.30,
        }, when="2026-08-25T10:05:00")

        runs = runlog.read_runs()
        assert len(runs) == 2, runs
        # Most recent first.
        assert runs[0]["format"] == "social", runs
        assert runs[1]["format"] == "blog", runs
        assert all("ts" in r for r in runs), runs

        s = runlog.summary()
        assert s["total"] == 2, s
        assert s["by_format"] == {"blog": 1, "social": 1}, s
        assert s["by_model"] == {"opus": 1, "haiku": 1}, s
        assert s["avg_duration_s"] == 3.0, s
        assert s["cache_hit_rate"] == 0.5, s
        assert s["gate_fail_rate"] == 0.5, s
        assert abs(s["total_cost_estimate"] - 0.40) < 1e-9, s
    finally:
        runlog.RUNLOG_PATH = orig
        try:
            tmp_path.unlink()
        except OSError:
            pass
        try:
            Path(tmpdir).rmdir()
        except OSError:
            pass


def test_runlog_missing_file():
    orig = runlog.RUNLOG_PATH
    runlog.RUNLOG_PATH = Path(tempfile.gettempdir()) / "no_such_runlog_xyz.jsonl"
    try:
        if runlog.RUNLOG_PATH.exists():
            runlog.RUNLOG_PATH.unlink()
        assert runlog.read_runs() == []
        assert runlog.summary()["total"] == 0
    finally:
        runlog.RUNLOG_PATH = orig


if __name__ == "__main__":
    test_analyze_basic()
    test_analyze_empty()
    test_within_target_and_complexity()
    test_code_and_tables_excluded()
    test_runlog_roundtrip()
    test_runlog_missing_file()
    print("OK")
