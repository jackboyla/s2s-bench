from __future__ import annotations

import wave

import pytest

from s2s_bench.audio import chunks, load_pcm16
from s2s_bench.models import AudioSpec, ConfigError


def test_synthetic_audio_is_deterministic() -> None:
    spec = AudioSpec("synthetic:440:100", sample_rate=1_000)
    first = load_pcm16(spec)
    assert first == load_pcm16(spec)
    assert len(first) == 200
    assert len(chunks(first, 1_000, 20)) == 5


def test_wav_rejects_wrong_sample_rate(tmp_path) -> None:
    path = tmp_path / "audio.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8_000)
        wav.writeframes(b"\0\0" * 10)
    with pytest.raises(ConfigError, match="8000 Hz"):
        load_pcm16(AudioSpec(str(path), sample_rate=16_000))


@pytest.mark.parametrize("source", ["synthetic:bad", "synthetic:nope:1", "synthetic:1:0"])
def test_invalid_synthetic_audio(source) -> None:
    with pytest.raises(ConfigError):
        load_pcm16(AudioSpec(source))


def test_missing_wav_is_clear(tmp_path) -> None:
    with pytest.raises(ConfigError, match="cannot read audio"):
        load_pcm16(AudioSpec(str(tmp_path / "missing.wav")))
