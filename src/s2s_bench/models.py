from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """A scenario is invalid."""


@dataclass(frozen=True)
class AudioSpec:
    source: str
    sample_rate: int = 24_000
    chunk_ms: int = 20
    pace: bool = True

    @classmethod
    def from_dict(cls, value: Any, base_dir: Path) -> AudioSpec:
        if isinstance(value, str):
            source = value
            data: dict[str, Any] = {}
        elif isinstance(value, dict):
            data = value
            source = str(data.get("source", ""))
        else:
            raise ConfigError("turn.audio must be a path, synthetic URI, or mapping")
        if not source:
            raise ConfigError("turn.audio.source is required")
        if not source.startswith("synthetic:"):
            path = Path(source)
            source = str(path if path.is_absolute() else (base_dir / path).resolve())
        sample_rate = int(data.get("sample_rate", 24_000))
        chunk_ms = int(data.get("chunk_ms", 20))
        if sample_rate <= 0 or chunk_ms <= 0:
            raise ConfigError("sample_rate and chunk_ms must be positive")
        return cls(source, sample_rate, chunk_ms, bool(data.get("pace", True)))


@dataclass(frozen=True)
class TurnSpec:
    name: str
    audio: AudioSpec
    cancel_after_first_audio_ms: int | None = None
    settle_ms: int = 100

    @classmethod
    def from_dict(cls, value: Any, index: int, base_dir: Path) -> TurnSpec:
        if not isinstance(value, dict):
            raise ConfigError(f"turns[{index}] must be a mapping")
        cancel = value.get("cancel_after_first_audio_ms")
        if cancel is not None and int(cancel) < 0:
            raise ConfigError("cancel_after_first_audio_ms cannot be negative")
        return cls(
            name=str(value.get("name", f"turn-{index + 1}")),
            audio=AudioSpec.from_dict(value.get("audio"), base_dir),
            cancel_after_first_audio_ms=None if cancel is None else int(cancel),
            settle_ms=int(value.get("settle_ms", 100)),
        )


@dataclass(frozen=True)
class LoadConfig:
    sessions: int = 1
    concurrency: int = 1
    ramp_up_s: float = 0.0


@dataclass(frozen=True)
class FaultConfig:
    send_jitter_ms: float = 0.0
    drop_audio_probability: float = 0.0
    seed: int = 7


@dataclass(frozen=True)
class Budget:
    metric: str
    percentile: str = "p95"
    max_ms: float | None = None
    min_rate: float | None = None


@dataclass(frozen=True)
class Scenario:
    name: str
    url: str
    turns: tuple[TurnSpec, ...]
    load: LoadConfig = LoadConfig()
    faults: FaultConfig = FaultConfig()
    timeout_s: float = 30.0
    headers: dict[str, str] = field(default_factory=dict)
    session: dict[str, Any] = field(default_factory=dict)
    budgets: tuple[Budget, ...] = ()
    source_path: str | None = None


@dataclass
class EventRecord:
    session_id: str
    turn_id: str | None
    direction: str
    event_type: str
    monotonic_ns: int
    elapsed_ms: float
    data: dict[str, Any]


@dataclass
class TurnResult:
    session_id: str
    turn_id: str
    turn_name: str
    status: str
    metrics_ms: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    protocol_violations: list[str] = field(default_factory=list)
    stale_events: int = 0
    events: list[EventRecord] = field(default_factory=list)

    def to_dict(self, *, include_events: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if not include_events:
            value.pop("events")
        return value


@dataclass
class RunResult:
    run_id: str
    scenario: str
    started_at: str
    duration_s: float
    turns: list[TurnResult]
    metadata: dict[str, Any]
    budget_results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(turn.status == "ok" for turn in self.turns) and all(
            item["passed"] for item in self.budget_results
        )
