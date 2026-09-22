from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from .models import AudioSpec, ConfigError


def load_pcm16(spec: AudioSpec) -> bytes:
    if spec.source.startswith("synthetic:"):
        return _synthetic_pcm(spec.source, spec.sample_rate)
    path = Path(spec.source)
    try:
        with wave.open(str(path), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                raise ConfigError(f"{path} must be mono 16-bit PCM WAV")
            if wav.getframerate() != spec.sample_rate:
                raise ConfigError(
                    f"{path} is {wav.getframerate()} Hz; scenario declares {spec.sample_rate} Hz"
                )
            return wav.readframes(wav.getnframes())
    except (OSError, wave.Error) as exc:
        raise ConfigError(f"cannot read audio {path}: {exc}") from exc


def _synthetic_pcm(uri: str, sample_rate: int) -> bytes:
    # synthetic:<frequency_hz>:<duration_ms> is deterministic test input for mock targets.
    parts = uri.split(":")
    if len(parts) != 3:
        raise ConfigError("synthetic audio must be synthetic:<frequency_hz>:<duration_ms>")
    try:
        frequency = float(parts[1])
        duration_ms = int(parts[2])
    except ValueError as exc:
        raise ConfigError(f"invalid synthetic audio URI: {uri}") from exc
    if frequency <= 0 or duration_ms <= 0:
        raise ConfigError("synthetic frequency and duration must be positive")
    count = round(sample_rate * duration_ms / 1000)
    samples = (
        round(10_000 * math.sin(2 * math.pi * frequency * index / sample_rate))
        for index in range(count)
    )
    return b"".join(struct.pack("<h", sample) for sample in samples)


def chunks(pcm: bytes, sample_rate: int, chunk_ms: int) -> list[bytes]:
    size = max(2, sample_rate * 2 * chunk_ms // 1000)
    size -= size % 2
    return [pcm[offset : offset + size] for offset in range(0, len(pcm), size)]
