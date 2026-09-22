from __future__ import annotations

import html
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import RunResult
from .stats import summarize


def write_artifacts(result: RunResult, output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary = summarize(result)
    paths = {
        "summary": output / "summary.json",
        "turns": output / "turns.json",
        "events": output / "events.jsonl",
        "trace": output / "trace.json",
        "prometheus": output / "metrics.prom",
        "markdown": output / "report.md",
        "html": output / "report.html",
    }
    paths["summary"].write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    paths["turns"].write_text(
        json.dumps([turn.to_dict(include_events=False) for turn in result.turns], indent=2) + "\n"
    )
    with paths["events"].open("w") as stream:
        for turn in result.turns:
            for event in turn.events:
                stream.write(json.dumps(asdict(event), sort_keys=True) + "\n")
    paths["trace"].write_text(json.dumps(_chrome_trace(result), separators=(",", ":")) + "\n")
    paths["prometheus"].write_text(_prometheus(summary))
    markdown = _markdown(summary)
    paths["markdown"].write_text(markdown)
    paths["html"].write_text(_html(summary))
    return paths


def _chrome_trace(result: RunResult) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for turn in result.turns:
        for event in turn.events:
            events.append(
                {
                    "name": event.event_type,
                    "cat": event.direction,
                    "ph": "i",
                    "s": "t",
                    "ts": event.elapsed_ms * 1000,
                    "pid": 1,
                    "tid": event.session_id,
                    "args": {"turn_id": event.turn_id, **event.data},
                }
            )
    return {"displayTimeUnit": "ms", "traceEvents": events}


def _prometheus(summary: dict[str, Any]) -> str:
    lines = [
        "# HELP s2s_bench_success_ratio Successful turns divided by attempted turns.",
        "# TYPE s2s_bench_success_ratio gauge",
        f"s2s_bench_success_ratio {summary['success_rate']:.9g}",
        "# HELP s2s_bench_protocol_violations_total Protocol ordering or state violations.",
        "# TYPE s2s_bench_protocol_violations_total gauge",
        f"s2s_bench_protocol_violations_total {summary['protocol_violations']}",
        "# HELP s2s_bench_latency_ms Voice pipeline latency in milliseconds.",
        "# TYPE s2s_bench_latency_ms gauge",
    ]
    for metric, distribution in summary["metrics_ms"].items():
        for stat in ("p50", "p95", "p99", "max", "mean"):
            lines.append(
                f's2s_bench_latency_ms{{metric="{metric}",stat="{stat}"}} {distribution[stat]:.9g}'
            )
    return "\n".join(lines) + "\n"


def _markdown(summary: dict[str, Any]) -> str:
    state = "PASS" if summary["passed"] else "FAIL"
    rows = ["| Metric | Count | p50 | p95 | p99 | Max |", "|---|---:|---:|---:|---:|---:|"]
    for name, value in summary["metrics_ms"].items():
        rows.append(
            f"| `{name}` | {value['count']} | {value['p50']:.1f} ms | {value['p95']:.1f} ms | "
            f"{value['p99']:.1f} ms | {value['max']:.1f} ms |"
        )
    budgets = ["| Budget | Actual | Limit | Result |", "|---|---:|---:|:---:|"]
    for item in summary["budgets"]:
        actual = "n/a" if item["actual"] is None else f"{item['actual']:.3g}"
        budgets.append(
            f"| `{item['metric']}:{item['stat']}` | {actual} | {item['operator']} {item['limit']} | "
            f"{'PASS' if item['passed'] else 'FAIL'} |"
        )
    return (
        f"# s2s-bench report: {summary['scenario']}\n\n"
        f"**{state}** — {summary['successful_turns']}/{summary['turns']} turns succeeded "
        f"in {summary['duration_s']:.2f}s.\n\n"
        + "\n".join(rows)
        + "\n\n## SLO budgets\n\n"
        + ("\n".join(budgets) if summary["budgets"] else "No budgets configured.")
        + f"\n\nProtocol violations: **{summary['protocol_violations']}**  \n"
        f"Stale events: **{summary['stale_events']}**\n"
    )


def _html(summary: dict[str, Any]) -> str:
    metric_rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{value['count']}</td><td>{value['p50']:.1f}</td>"
        f"<td>{value['p95']:.1f}</td><td>{value['p99']:.1f}</td><td>{value['max']:.1f}</td></tr>"
        for name, value in summary["metrics_ms"].items()
    )
    budget_rows = "".join(
        f"<tr><td>{html.escape(item['metric'])}:{html.escape(item['stat'])}</td>"
        f"<td>{item['actual'] if item['actual'] is not None else 'n/a'}</td>"
        f"<td>{item['operator']} {item['limit']}</td>"
        f"<td class={'pass' if item['passed'] else 'fail'}>{'PASS' if item['passed'] else 'FAIL'}</td></tr>"
        for item in summary["budgets"]
    )
    state = "PASS" if summary["passed"] else "FAIL"
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>s2s-bench — {html.escape(summary["scenario"])}</title>
<style>
:root {{ color-scheme: light dark; font-family: ui-monospace, SFMono-Regular, monospace; }}
body {{ max-width: 1100px; margin: 3rem auto; padding: 0 1rem; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:1rem; }}
.card {{ border:1px solid #8886; border-radius:10px; padding:1rem; }}
.value {{ font-size:1.8rem; margin-top:.4rem; }} table {{ width:100%; border-collapse:collapse; margin:1rem 0 2rem; }}
th,td {{ text-align:right; padding:.65rem; border-bottom:1px solid #8885; }} th:first-child,td:first-child {{ text-align:left; }}
.pass {{ color:#20a060; }} .fail {{ color:#e14b4b; }} code {{ font-size:.9em; }}
</style>
<h1>s2s-bench <span class="{"pass" if summary["passed"] else "fail"}">{state}</span></h1>
<p>{html.escape(summary["scenario"])} · <code>{summary["run_id"]}</code></p>
<div class="cards">
<div class="card">Success<div class="value">{summary["success_rate"]:.1%}</div></div>
<div class="card">Turns<div class="value">{summary["turns"]}</div></div>
<div class="card">Sessions<div class="value">{summary["sessions"]}</div></div>
<div class="card">Wall time<div class="value">{summary["duration_s"]:.2f}s</div></div>
<div class="card">Violations<div class="value">{summary["protocol_violations"]}</div></div>
<div class="card">Stale events<div class="value">{summary["stale_events"]}</div></div>
</div>
<h2>Latency (ms)</h2><table><thead><tr><th>Metric</th><th>N</th><th>p50</th><th>p95</th><th>p99</th><th>max</th></tr></thead><tbody>{metric_rows}</tbody></table>
<h2>SLO budgets</h2><table><thead><tr><th>Budget</th><th>Actual</th><th>Limit</th><th>Result</th></tr></thead><tbody>{budget_rows or '<tr><td colspan="4">No budgets configured</td></tr>'}</tbody></table>
<p>Open <code>trace.json</code> in Perfetto or Chrome tracing to inspect each wire event.</p>
</html>"""


def compare_summaries(base: dict[str, Any], candidate: dict[str, Any]) -> str:
    names = sorted(set(base.get("metrics_ms", {})) | set(candidate.get("metrics_ms", {})))
    rows = ["| Metric p95 | Base | Candidate | Delta |", "|---|---:|---:|---:|"]
    for name in names:
        old = base.get("metrics_ms", {}).get(name, {}).get("p95")
        new = candidate.get("metrics_ms", {}).get(name, {}).get("p95")
        if old is None or new is None:
            rows.append(f"| `{name}` | {old or 'n/a'} | {new or 'n/a'} | n/a |")
        else:
            delta = new - old
            percent = delta / old * 100 if old else 0.0
            rows.append(
                f"| `{name}` | {old:.1f} ms | {new:.1f} ms | {delta:+.1f} ms ({percent:+.1f}%) |"
            )
    return "# s2s-bench comparison\n\n" + "\n".join(rows) + "\n"
