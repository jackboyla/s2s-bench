# Session plan

## Ongoing instructions

- Build plan 2: an infra-grade realtime voice-agent benchmark and fault harness.
- Target Hugging Face `speech-to-speech` through its OpenAI Realtime WebSocket API.
- Keep runs reproducible, document rerunnable commands, and preserve an append-only experiment log.
- Use Jack Boylan's Git identity and do not add co-author trailers.

## Current plan

1. Inspect the current upstream protocol and established voice/load-test patterns.
2. Define a small, typed benchmark contract around sessions, turns, events, and SLOs.
3. Implement the async load runner, protocol adapter, faults, metrics, traces, and reports.
4. Add a deterministic mock server, tests, CI, packaging, examples, and docs.
5. Run the full suite and sample benchmarks, then record results.

## Decisions

- Use the OpenAI Realtime GA WebSocket event set as the wire contract.
- Keep the load engine native `asyncio`; session-per-task maps cleanly to realtime connections.
- Capture raw event timelines before deriving metrics so results remain auditable.
- Provide a deterministic mock target so contributors can test the harness in CI without models or keys.
- Export machine-readable JSON, JSONL event traces, Markdown, and a self-contained HTML report.

## Status

- Repository, package, docs, examples, CI, mock target, and report pipeline complete.
- Strict lint, format, mypy, 30 tests, and the 90% coverage gate pass.
- Positive smoke: 16/16 turns passed at concurrency four.
- Negative stale-output drill: all eight injected violations detected; CLI exited 2.
- Live Hugging Face run attempted and recorded; backend initialization did not reach readiness, so no real latency claim was made.

## Outstanding

- Debug the local `speech-to-speech` backend startup before publishing live model numbers.
- Add WebRTC and server-VAD overlapping-speech actions in later releases.

## Commands run

- Workstation health checks from `AGENTS.md`.
- `rg`/`sed` inspection of the local `speech-to-speech` realtime protocol.
- Web research of LiveKit voice metrics/testing, Pipecat latency metrics, Locust load patterns, and OpenTelemetry conventions.

## Artifacts

- `progress/plan.md`
- `progress/experiment-log.md`
- `progress/evaluations/hf-local.yaml`
- `progress/logs/hf-real-server.log`
- `artifacts/smoke/` (ignored generated output)
- `artifacts/stale-drill/` (ignored generated output)
