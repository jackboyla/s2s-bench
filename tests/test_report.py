from __future__ import annotations

import json

from s2s_bench.models import EventRecord, RunResult, TurnResult
from s2s_bench.report import compare_summaries, write_artifacts


def test_all_artifacts_are_written(tmp_path) -> None:
    event = EventRecord("s1", "t1", "received", "response.done", 1, 1.0, {"type": "response.done"})
    result = RunResult(
        "run",
        "scenario",
        "now",
        0.1,
        [TurnResult("s1", "t1", "turn", "ok", {"e2e_first_audio": 42}, events=[event])],
        {},
    )
    paths = write_artifacts(result, tmp_path)
    assert set(paths) == {"summary", "turns", "events", "trace", "prometheus", "markdown", "html"}
    assert json.loads(paths["summary"].read_text())["passed"] is True
    assert "traceEvents" in paths["trace"].read_text()
    assert "s2s_bench_latency_ms" in paths["prometheus"].read_text()


def test_compare_reports_delta() -> None:
    report = compare_summaries(
        {"metrics_ms": {"e2e": {"p95": 100}}},
        {"metrics_ms": {"e2e": {"p95": 110}}},
    )
    assert "+10.0 ms (+10.0%)" in report


def test_compare_handles_missing_metric() -> None:
    report = compare_summaries(
        {"metrics_ms": {"old": {"p95": 10}}},
        {"metrics_ms": {"new": {"p95": 12}}},
    )
    assert report.count("n/a") == 4
