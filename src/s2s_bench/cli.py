from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import __version__
from .config import load_scenario
from .mock_server import MockConfig, run_mock_server
from .models import ConfigError
from .report import compare_summaries, write_artifacts
from .runner import run_scenario
from .stats import evaluate_budgets


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="s2s-bench", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run a benchmark scenario")
    run.add_argument("scenario", type=Path)
    run.add_argument("--url", help="override target.url")
    run.add_argument("--output", type=Path, default=Path("artifacts/latest"))

    mock = commands.add_parser("mock", help="run a deterministic Realtime protocol target")
    mock.add_argument("--host", default="127.0.0.1")
    mock.add_argument("--port", type=int, default=9876)
    mock.add_argument("--stt-ms", type=int, default=40)
    mock.add_argument("--llm-ms", type=int, default=60)
    mock.add_argument("--tts-ms", type=int, default=30)
    mock.add_argument("--stale-audio-after-cancel", action="store_true")
    mock.add_argument("--fail-every", type=int, default=0)

    compare = commands.add_parser("compare", help="compare two summary.json artifacts")
    compare.add_argument("base", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--output", type=Path)
    return parser


async def _run(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario, url_override=args.url)
    print(
        f"running {scenario.name}: {scenario.load.sessions} sessions, "
        f"concurrency {scenario.load.concurrency}, target {scenario.url}"
    )
    result = await run_scenario(scenario)
    result.budget_results = evaluate_budgets(result, scenario.budgets)
    paths = write_artifacts(result, args.output)
    successes = sum(turn.status == "ok" for turn in result.turns)
    print(
        f"{'PASS' if result.passed else 'FAIL'}: {successes}/{len(result.turns)} turns in {result.duration_s:.2f}s"
    )
    print(f"report: {paths['markdown']}")
    return 0 if result.passed else 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "run":
            return asyncio.run(_run(args))
        if args.command == "mock":
            config = MockConfig(
                host=args.host,
                port=args.port,
                stt_ms=args.stt_ms,
                llm_ms=args.llm_ms,
                tts_ms=args.tts_ms,
                stale_audio_after_cancel=args.stale_audio_after_cancel,
                fail_every=args.fail_every,
            )
            asyncio.run(run_mock_server(config))
            return 0
        base = json.loads(args.base.read_text())
        candidate = json.loads(args.candidate.read_text())
        report = compare_summaries(base, candidate)
        if args.output:
            args.output.write_text(report)
        else:
            print(report, end="")
        return 0
    except (ConfigError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
