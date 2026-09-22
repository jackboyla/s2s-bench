from __future__ import annotations

from s2s_bench.models import Budget, RunResult, TurnResult
from s2s_bench.stats import evaluate_budgets, percentile, summarize


def result() -> RunResult:
    return RunResult(
        run_id="run",
        scenario="test",
        started_at="now",
        duration_s=1,
        turns=[
            TurnResult("s1", "t1", "one", "ok", {"e2e_first_audio": 100}),
            TurnResult("s2", "t2", "two", "failed", {"e2e_first_audio": 200}),
        ],
        metadata={},
    )


def test_percentile_interpolates() -> None:
    assert percentile([0, 100], 0.95) == 95


def test_summary_and_budgets() -> None:
    run = result()
    summary = summarize(run)
    assert summary["success_rate"] == 0.5
    assert summary["metrics_ms"]["e2e_first_audio"]["p50"] == 150
    budgets = evaluate_budgets(
        run,
        (
            Budget("success_rate", min_rate=0.5),
            Budget("e2e_first_audio", percentile="p95", max_ms=196),
        ),
    )
    assert [item["passed"] for item in budgets] == [True, True]
