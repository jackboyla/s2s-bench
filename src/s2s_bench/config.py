from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .models import Budget, ConfigError, FaultConfig, LoadConfig, Scenario, TurnSpec


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a mapping")
    return value


def load_scenario(path: str | Path, *, url_override: str | None = None) -> Scenario:
    source = Path(path).resolve()
    try:
        raw = yaml.safe_load(source.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read scenario {source}: {exc}") from exc
    data = _mapping(raw, "scenario")
    if int(data.get("version", 1)) != 1:
        raise ConfigError("only scenario version 1 is supported")

    target = _mapping(data.get("target"), "target")
    url = url_override or str(target.get("url", ""))
    if not url.startswith(("ws://", "wss://")):
        raise ConfigError("target.url must start with ws:// or wss://")

    headers = {
        str(k): os.path.expandvars(str(v))
        for k, v in _mapping(target.get("headers"), "headers").items()
    }
    load = _mapping(data.get("load"), "load")
    load_config = LoadConfig(
        sessions=int(load.get("sessions", 1)),
        concurrency=int(load.get("concurrency", 1)),
        ramp_up_s=float(load.get("ramp_up_s", 0.0)),
    )
    if load_config.sessions < 1 or load_config.concurrency < 1:
        raise ConfigError("load sessions and concurrency must be positive")
    if load_config.concurrency > load_config.sessions:
        raise ConfigError("load.concurrency cannot exceed load.sessions")

    faults = _mapping(data.get("faults"), "faults")
    fault_config = FaultConfig(
        send_jitter_ms=float(faults.get("send_jitter_ms", 0.0)),
        drop_audio_probability=float(faults.get("drop_audio_probability", 0.0)),
        seed=int(faults.get("seed", 7)),
    )
    if not 0 <= fault_config.drop_audio_probability <= 1:
        raise ConfigError("faults.drop_audio_probability must be between 0 and 1")

    raw_turns = data.get("turns")
    if not isinstance(raw_turns, list) or not raw_turns:
        raise ConfigError("turns must be a non-empty list")
    turns = tuple(
        TurnSpec.from_dict(value, index, source.parent) for index, value in enumerate(raw_turns)
    )

    raw_budgets = data.get("budgets", [])
    if not isinstance(raw_budgets, list):
        raise ConfigError("budgets must be a list")
    budgets: list[Budget] = []
    for item in raw_budgets:
        value = _mapping(item, "budget")
        metric = str(value.get("metric", ""))
        if not metric:
            raise ConfigError("budget.metric is required")
        max_ms = value.get("max_ms")
        min_rate = value.get("min_rate")
        if (max_ms is None) == (min_rate is None):
            raise ConfigError(f"budget {metric} needs exactly one of max_ms or min_rate")
        budgets.append(
            Budget(
                metric=metric,
                percentile=str(value.get("percentile", "p95")),
                max_ms=None if max_ms is None else float(max_ms),
                min_rate=None if min_rate is None else float(min_rate),
            )
        )

    return Scenario(
        name=str(data.get("name", source.stem)),
        url=url,
        turns=turns,
        load=load_config,
        faults=fault_config,
        timeout_s=float(data.get("timeout_s", 30.0)),
        headers=headers,
        session=_mapping(data.get("session"), "session"),
        budgets=tuple(budgets),
        source_path=str(source),
    )
