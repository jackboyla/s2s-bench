# Experiment log

Append-only ledger for meaningful benchmark and validation runs.

## 2026-09-22—validation-001

### Intent

Validate the package, type surface, style, and branch-aware test coverage before a CLI run.

### Environment

- Machine: `radiance-ws`
- GPUs used: none
- CUDA_VISIBLE_DEVICES: unset
- Git commit: not yet committed
- Branch: `main`
- Python environment: project `.venv`, Python 3.12.3, uv 0.11.28
- Docker image, if applicable: none

### Resource check before launch

```bash
hostname
uptime
df -h
free -h
nvidia-smi
docker ps
tmux ls || true
```

Both RTX 5090 GPUs were idle at the first check. The root filesystem had 229 GB free.

### Commands

#### Setup

```bash
uv sync --all-extras --dev
```

#### Diagnostics

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

#### Eval

```bash
uv run pytest --cov --cov-report=term-missing
```

### Artifacts

- Logs: terminal output only
- Checkpoints: none
- Predictions: none
- Metrics: 30 tests; 90.77% branch-aware coverage
- Eval summary: lint, format, strict mypy, tests, and coverage gate passed
- GPU metrics: not applicable

### Result

Base: no prior run

Candidate: all checks passed; 30 tests passed in 0.49 seconds

Delta:

- Wins / losses: package and integration paths validated
- Failure modes: none in final run
- GPU utilization: not applicable
- Memory usage: not measured for this CPU-only run
- Runtime: under one second for tests

### Decision

Keep.

### Notes

- Repeated-output diagnostics? no
- GPU utilization or memory issue? no
- Data issue? no
- Code issue? an earlier run exposed a wrong post-pacing VAD anchor; fixed before this run
- Anything to change next? run public CLI smoke and negative drill

## 2026-09-22—mock-smoke-001

### Intent

Exercise the installed CLI, concurrent scheduler, metric attribution, SLO gate, and every report format against fixed stage delays.

### Environment

- Machine: `radiance-ws`
- GPUs used: none
- CUDA_VISIBLE_DEVICES: unset
- Git commit: not yet committed
- Branch: `main`
- Python environment: project `.venv`, Python 3.12.3
- Docker image, if applicable: none

### Resource check before launch

```bash
nvidia-smi
docker ps
tmux ls || true
ps -eo user,pid,pgid,stat,etime,%cpu,%mem,cmd --sort=-%mem | head -30
```

No benchmark GPU job was active. An unrelated llama.cpp container appeared after the first workstation check and was left untouched.

### Commands

#### Inference

```bash
uv run s2s-bench mock
uv run s2s-bench run examples/mock-smoke.yaml --output artifacts/smoke
```

#### Diagnostics

```bash
python3 -m json.tool artifacts/smoke/summary.json >/dev/null
wc -l artifacts/smoke/events.jsonl
du -h artifacts/smoke/*
```

#### Eval

```bash
sed -n '1,80p' artifacts/smoke/report.md
```

### Artifacts

- Logs: `artifacts/smoke/events.jsonl` (280 wire events)
- Checkpoints: none
- Predictions: transcripts retained in event log
- Metrics: `artifacts/smoke/summary.json`, `metrics.prom`
- Eval summary: `artifacts/smoke/report.md`, `report.html`
- GPU metrics: not applicable

### Result

Base: configured mock delays of 50 ms end silence, 40 ms STT, 60 ms LLM, and 30 ms TTS

Candidate: 16/16 turns passed across eight sessions at concurrency four

Delta:

- Wins / losses: zero protocol violations and zero stale events
- Failure modes: none
- GPU utilization: not applicable
- Memory usage: not measured
- Runtime: 1.95 seconds
- p95 VAD finalization: 52.7 ms
- p95 STT final: 41.3 ms
- p95 LLM first text: 61.6 ms
- p95 TTS first audio: 31.7 ms
- p95 end-to-end first audio: 134.0 ms
- p95 cancellation: 0.6 ms

### Decision

Keep as the checked-in smoke scenario and CI gate.

### Notes

- Repeated-output diagnostics? no
- GPU utilization or memory issue? no
- Data issue? synthetic fixtures are only valid for the mock target
- Code issue? no
- Anything to change next? inject stale output and confirm a non-zero exit

## 2026-09-22—stale-drill-001

### Intent

Prove that audio emitted after terminal cancellation fails the affected turns and the process exit code.

### Environment

- Machine: `radiance-ws`
- GPUs used: none
- CUDA_VISIBLE_DEVICES: unset
- Git commit: not yet committed
- Branch: `main`
- Python environment: project `.venv`, Python 3.12.3
- Docker image, if applicable: none

### Resource check before launch

Same CPU-only state as `mock-smoke-001`.

### Commands

#### Inference

```bash
uv run s2s-bench mock --stale-audio-after-cancel
uv run s2s-bench run examples/mock-smoke.yaml --output artifacts/stale-drill
```

#### Eval

```bash
test "$?" -eq 2
sed -n '1,90p' artifacts/stale-drill/report.md
```

### Artifacts

- Logs: `artifacts/stale-drill/events.jsonl`
- Checkpoints: none
- Predictions: none
- Metrics: `artifacts/stale-drill/summary.json`
- Eval summary: `artifacts/stale-drill/report.md`
- GPU metrics: not applicable

### Result

Base: clean mock run with no output after terminal events

Candidate: one stale audio event injected after each of eight cancelled turns

Delta:

- Wins / losses: detector found all eight injected events
- Failure modes: 8/16 turns failed; success-rate budget failed; CLI exited 2
- GPU utilization: not applicable
- Memory usage: not measured
- Runtime: 1.94 seconds

### Decision

Keep the detector and negative drill.

### Notes

- Repeated-output diagnostics? no
- GPU utilization or memory issue? no
- Data issue? no
- Code issue? no
- Anything to change next? validate a live Hugging Face stack

## 2026-09-22—hf-local-001

### Intent

Run the harness against Hugging Face `speech-to-speech` with local Faster Whisper ASR, an existing llama.cpp Gemma backend, and local TTS. Compare the cold and warm turns.

### Environment

- Machine: `radiance-ws`
- GPUs used: physical GPU 0 selected for speech backends; an existing llama.cpp process already held about 3.9 GB there
- CUDA_VISIBLE_DEVICES: `0`
- Git commit: local `speech-to-speech` branch `fix/issue-308-turn-order`; benchmark not yet committed
- Branch: `main` for `s2s-bench`
- Python environment: `speech-to-speech/.venv`, Python 3.11
- Docker image, if applicable: existing `ghcr.io/ggml-org/llama.cpp:server-cuda` backend, not launched or changed by this run

### Resource check before launch

```bash
nvidia-smi
docker ps
tmux ls || true
ps -eo user,pid,pgid,stat,etime,%cpu,%mem,cmd --sort=-%mem | head -30
```

### Commands

#### Setup

```bash
cd /home/jack/workspace/Desktop/speech-to-speech
uv sync --extra faster-whisper --extra kokoro
```

#### Inference

```bash
CUDA_VISIBLE_DEVICES=0 uv run speech-to-speech serve \
  --stt faster-whisper \
  --faster_whisper_stt_model_name Systran/faster-whisper-base \
  --llm_backend chat-completions \
  --model_name local-gemma \
  --responses_api_base_url http://127.0.0.1:18080/v1 \
  --responses_api_api_key not-needed \
  --tts kokoro \
  --num_pipelines 1 \
  --no_smart_turn \
  --port 18765
```

A second launch changed ASR to CPU int8 and TTS to `facebookMMS` to isolate startup.

#### Diagnostics

```bash
tail -200 progress/logs/hf-real-server.log
ss -ltnp | rg ':18765'
nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu,power.draw --format=csv,noheader
```

### Artifacts

- Logs: `progress/logs/hf-real-server.log`
- Checkpoints: persistent Hugging Face cache
- Predictions: none; server never became ready
- Metrics: llama.cpp warm-up request completed in 0.124 seconds
- Eval summary: no benchmark result
- GPU metrics: GPU 0 rose from about 3.9 GB to 5.0 GB during backend load; utilization returned to 0%

### Result

Base: deterministic mock adapter passed

Candidate: blocked before the Realtime listener opened

Delta:

- Wins / losses: confirmed the existing local LLM endpoint; did not get a full audio turn
- Failure modes: first attempt stalled during a Kokoro Xet-backed weight fetch/load; the CPU-ASR and Facebook MMS isolation attempt also stalled before handler readiness
- GPU utilization: brief load only; no inference sample
- Memory usage: about 1.1 GB extra GPU memory during handler startup
- Runtime: stopped after bounded startup checks

### Decision

Reject the run as benchmark evidence. Keep the scenario and logs for follow-up; do not report fabricated latency numbers.

### Notes

- Repeated-output diagnostics? no
- GPU utilization or memory issue? no out-of-memory error
- Data issue? the source WAV was converted to mono PCM16 at 24 kHz with trailing silence
- Code issue? no harness error observed
- Anything to change next? debug upstream handler initialization separately, then rerun `progress/evaluations/hf-local.yaml`
