from __future__ import annotations

import json

import pytest

from s2s_bench import cli


def test_compare_command_writes_report(tmp_path) -> None:
    base = tmp_path / "base.json"
    candidate = tmp_path / "candidate.json"
    output = tmp_path / "comparison.md"
    base.write_text(json.dumps({"metrics_ms": {"e2e": {"p95": 10}}}))
    candidate.write_text(json.dumps({"metrics_ms": {"e2e": {"p95": 12}}}))
    assert cli.main(["compare", str(base), str(candidate), "--output", str(output)]) == 0
    assert "+2.0 ms" in output.read_text()


def test_compare_command_prints_report(tmp_path, capsys) -> None:
    base = tmp_path / "base.json"
    candidate = tmp_path / "candidate.json"
    base.write_text('{"metrics_ms": {}}')
    candidate.write_text('{"metrics_ms": {}}')
    assert cli.main(["compare", str(base), str(candidate)]) == 0
    assert "s2s-bench comparison" in capsys.readouterr().out


def test_invalid_scenario_is_a_cli_error(tmp_path, capsys) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("version: 99")
    assert cli.main(["run", str(path)]) == 2
    assert "only scenario version 1" in capsys.readouterr().err


def test_run_and_mock_dispatch(monkeypatch, tmp_path) -> None:
    scenario = tmp_path / "valid.yaml"
    scenario.write_text(
        "version: 1\ntarget: {url: 'ws://127.0.0.1'}\nturns: [{audio: 'synthetic:1:1'}]\n"
    )

    async def fake_run(_args):
        return 7

    async def fake_mock(_config):
        return None

    monkeypatch.setattr(cli, "_run", fake_run)
    monkeypatch.setattr(cli, "run_mock_server", fake_mock)
    assert cli.main(["run", str(scenario)]) == 7
    assert cli.main(["mock", "--port", "9999", "--fail-every", "3"]) == 0


def test_keyboard_interrupt_returns_shell_code(monkeypatch, tmp_path) -> None:
    scenario = tmp_path / "valid.yaml"
    scenario.write_text(
        "version: 1\ntarget: {url: 'ws://127.0.0.1'}\nturns: [{audio: 'synthetic:1:1'}]\n"
    )

    async def interrupted(_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_run", interrupted)
    assert cli.main(["run", str(scenario)]) == 130


def test_version_flag(capsys) -> None:
    with pytest.raises(SystemExit, match="0"):
        cli.main(["--version"])
    assert "0.1.0" in capsys.readouterr().out
