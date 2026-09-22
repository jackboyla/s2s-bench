from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from .models import Budget, RunResult


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile needs at least one value")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * quantile
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def summarize(result: RunResult) -> dict[str, Any]:
    metrics: dict[str, list[float]] = defaultdict(list)
    for turn in result.turns:
        for name, value in turn.metrics_ms.items():
            metrics[name].append(value)
    distributions = {
        name: {
            "count": len(values),
            "min": min(values),
            "p50": percentile(values, 0.50),
            "p95": percentile(values, 0.95),
            "p99": percentile(values, 0.99),
            "max": max(values),
            "mean": sum(values) / len(values),
        }
        for name, values in sorted(metrics.items())
    }
    total = len(result.turns)
    successes = sum(turn.status == "ok" for turn in result.turns)
    return {
        "run_id": result.run_id,
        "scenario": result.scenario,
        "started_at": result.started_at,
        "duration_s": result.duration_s,
        "passed": result.passed,
        "sessions": len({turn.session_id for turn in result.turns}),
        "turns": total,
        "successful_turns": successes,
        "success_rate": successes / total if total else 0.0,
        "protocol_violations": sum(len(turn.protocol_violations) for turn in result.turns),
        "stale_events": sum(turn.stale_events for turn in result.turns),
        "metrics_ms": distributions,
        "budgets": result.budget_results,
        "metadata": result.metadata,
    }


def evaluate_budgets(result: RunResult, budgets: tuple[Budget, ...]) -> list[dict[str, Any]]:
    summary = summarize(result)
    evaluated: list[dict[str, Any]] = []
    for budget in budgets:
        actual: float | None
        limit: float | None
        if budget.min_rate is not None:
            actual = float(summary.get(budget.metric, 0.0))
            passed = actual >= budget.min_rate
            limit = budget.min_rate
            operator = ">="
        else:
            distribution = summary["metrics_ms"].get(budget.metric, {})
            actual_value = distribution.get(budget.percentile)
            actual = None if actual_value is None else float(actual_value)
            passed = actual is not None and budget.max_ms is not None and actual <= budget.max_ms
            limit = budget.max_ms
            operator = "<="
        evaluated.append(
            {
                "metric": budget.metric,
                "stat": budget.percentile if budget.max_ms is not None else "rate",
                "actual": actual,
                "operator": operator,
                "limit": limit,
                "passed": passed,
            }
        )
    return evaluated
