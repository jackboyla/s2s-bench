from __future__ import annotations

import base64
import hashlib
from typing import Any

SPEECH_STARTED = "input_audio_buffer.speech_started"
SPEECH_STOPPED = "input_audio_buffer.speech_stopped"
TRANSCRIPT_DONE = "conversation.item.input_audio_transcription.completed"
RESPONSE_CREATED = "response.created"
RESPONSE_DONE = "response.done"
AUDIO_DELTA_TYPES = {"response.output_audio.delta", "response.audio.delta"}
TEXT_DELTA_TYPES = {
    "response.output_audio_transcript.delta",
    "response.audio_transcript.delta",
    "response.output_text.delta",
}


def audio_append(chunk: bytes) -> dict[str, str]:
    return {
        "type": "input_audio_buffer.append",
        "audio": base64.b64encode(chunk).decode("ascii"),
    }


def public_event(event: dict[str, Any]) -> dict[str, Any]:
    """Strip large audio bodies while retaining enough data to audit a trace."""
    clean = dict(event)
    audio = (
        clean.get("audio") or clean.get("delta")
        if clean.get("type") in AUDIO_DELTA_TYPES | {"input_audio_buffer.append"}
        else None
    )
    if isinstance(audio, str):
        clean.pop("audio", None)
        clean.pop("delta", None)
        clean["audio_base64_bytes"] = len(audio)
        clean["audio_sha256_12"] = hashlib.sha256(audio.encode()).hexdigest()[:12]
    return clean


def response_status(event: dict[str, Any]) -> str | None:
    response = event.get("response")
    return (
        str(response.get("status"))
        if isinstance(response, dict) and response.get("status")
        else None
    )
