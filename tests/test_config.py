from __future__ import annotations

import pytest

from s2s_bench.config import load_scenario
from s2s_bench.models import ConfigError


def test_load_scenario_expands_header_and_resolves_audio(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BENCH_TOKEN", "secret")
    path = tmp_path / "scenario.yaml"
    path.write_text(
        """
version: 1
target:
  url: ws://localhost:9000/v1/realtime
  headers: {Authorization: "Bearer ${BENCH_TOKEN}"}
load: {sessions: 2, concurrency: 1}
turns:
  - audio: voice.wav
budgets:
  - {metric: success_rate, min_rate: 0.99}
"""
    )
    scenario = load_scenario(path)
    assert scenario.headers == {"Authorization": "Bearer secret"}
    assert scenario.turns[0].audio.source == str((tmp_path / "voice.wav").resolve())
    assert scenario.budgets[0].min_rate == 0.99


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("load: {sessions: 1, concurrency: 2}", "cannot exceed"),
        ("faults: {drop_audio_probability: 1.1}", "between 0 and 1"),
        ("budgets: [{metric: x, max_ms: 1, min_rate: 1}]", "exactly one"),
    ],
)
def test_invalid_scenario(tmp_path, extra, message) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        f"version: 1\ntarget: {{url: 'ws://localhost'}}\nturns: [{{audio: 'synthetic:1:1'}}]\n{extra}\n"
    )
    with pytest.raises(ConfigError, match=message):
        load_scenario(path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("[]", "scenario must be a mapping"),
        ("version: 1\ntarget: {url: http://bad}\nturns: []", "must start"),
        ("version: 1\ntarget: {url: ws://ok}\nturns: []", "non-empty"),
        ("version: 1\ntarget: {url: ws://ok}\nturns: [bad]", r"turns\[0\]"),
        ("version: 1\ntarget: {url: ws://ok}\nturns: [{audio: null}]", "turn.audio"),
    ],
)
def test_other_invalid_shapes(tmp_path, body, message) -> None:
    path = tmp_path / "bad-shape.yaml"
    path.write_text(body)
    with pytest.raises(ConfigError, match=message):
        load_scenario(path)
