from __future__ import annotations

import asyncio
import base64
import json
import uuid
from dataclasses import dataclass
from typing import Any

from websockets.asyncio.server import ServerConnection, serve


@dataclass(frozen=True)
class MockConfig:
    host: str = "127.0.0.1"
    port: int = 9876
    end_silence_ms: int = 50
    stt_ms: int = 40
    llm_ms: int = 60
    tts_ms: int = 30
    audio_chunks: int = 3
    chunk_gap_ms: int = 10
    stale_audio_after_cancel: bool = False
    fail_every: int = 0


class MockRealtimeServer:
    """Deterministic protocol target for harness tests and CI smoke runs."""

    def __init__(self, config: MockConfig) -> None:
        self.config = config
        self.turn_count = 0

    async def handler(self, websocket: ServerConnection) -> None:
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        await self._send(
            websocket,
            {"type": "session.created", "session": {"id": session_id, "type": "realtime"}},
        )
        speech_active = False
        finalize_task: asyncio.Task[None] | None = None
        response_task: asyncio.Task[None] | None = None
        response_id: str | None = None

        async def cancel_response(reason: str) -> None:
            nonlocal response_task, response_id
            if response_task is None or response_task.done() or response_id is None:
                return
            response_task.cancel()
            await asyncio.gather(response_task, return_exceptions=True)
            await self._send(
                websocket,
                {
                    "type": "response.done",
                    "response": {
                        "id": response_id,
                        "status": "cancelled",
                        "status_details": {"reason": reason},
                        "output": [],
                    },
                },
            )
            if self.config.stale_audio_after_cancel:
                await self._send_audio(websocket, response_id, index=999)
            response_task = None
            response_id = None

        async def finalize() -> None:
            nonlocal speech_active, response_task, response_id
            await asyncio.sleep(self.config.end_silence_ms / 1000)
            speech_active = False
            self.turn_count += 1
            item_id = f"item_{uuid.uuid4().hex[:8]}"
            await self._send(
                websocket,
                {"type": "input_audio_buffer.speech_stopped", "item_id": item_id},
            )
            await asyncio.sleep(self.config.stt_ms / 1000)
            await self._send(
                websocket,
                {
                    "type": "conversation.item.input_audio_transcription.completed",
                    "item_id": item_id,
                    "transcript": "synthetic benchmark utterance",
                },
            )
            response_id = f"resp_{uuid.uuid4().hex[:8]}"
            if self.config.fail_every and self.turn_count % self.config.fail_every == 0:
                await self._send(
                    websocket,
                    {
                        "type": "response.done",
                        "response": {"id": response_id, "status": "failed", "output": []},
                    },
                )
                return
            await self._send(
                websocket,
                {
                    "type": "response.created",
                    "response": {"id": response_id, "status": "in_progress"},
                },
            )
            response_task = asyncio.create_task(
                self._generate(websocket, response_id), name=f"mock-{response_id}"
            )

        try:
            async for raw in websocket:
                if not isinstance(raw, str):
                    continue
                event = json.loads(raw)
                event_type = event.get("type")
                if event_type == "session.update":
                    await self._send(
                        websocket,
                        {"type": "session.updated", "session": event.get("session", {})},
                    )
                elif event_type == "input_audio_buffer.append":
                    if response_task is not None and not response_task.done():
                        await cancel_response("turn_detected")
                    if not speech_active:
                        speech_active = True
                        await self._send(
                            websocket,
                            {"type": "input_audio_buffer.speech_started", "audio_start_ms": 0},
                        )
                    if finalize_task is not None:
                        finalize_task.cancel()
                    finalize_task = asyncio.create_task(finalize())
                elif event_type == "response.cancel":
                    await cancel_response("client_cancelled")
                else:
                    await self._send(
                        websocket,
                        {"type": "error", "error": {"type": "unknown_or_invalid_event"}},
                    )
        finally:
            for task in (finalize_task, response_task):
                if task is not None:
                    task.cancel()
            await asyncio.gather(
                *(task for task in (finalize_task, response_task) if task is not None),
                return_exceptions=True,
            )

    async def _generate(self, websocket: ServerConnection, response_id: str) -> None:
        await asyncio.sleep(self.config.llm_ms / 1000)
        item_id = f"out_{uuid.uuid4().hex[:8]}"
        await self._send(
            websocket,
            {
                "type": "response.output_audio_transcript.delta",
                "response_id": response_id,
                "item_id": item_id,
                "delta": "Benchmark response.",
            },
        )
        await asyncio.sleep(self.config.tts_ms / 1000)
        for index in range(self.config.audio_chunks):
            await self._send_audio(websocket, response_id, index)
            await asyncio.sleep(self.config.chunk_gap_ms / 1000)
        await self._send(
            websocket,
            {"type": "response.output_audio.done", "response_id": response_id, "item_id": item_id},
        )
        await self._send(
            websocket,
            {
                "type": "response.output_audio_transcript.done",
                "response_id": response_id,
                "item_id": item_id,
                "transcript": "Benchmark response.",
            },
        )
        await self._send(
            websocket,
            {
                "type": "response.done",
                "response": {"id": response_id, "status": "completed", "output": []},
            },
        )

    @staticmethod
    async def _send(websocket: ServerConnection, event: dict[str, Any]) -> None:
        await websocket.send(json.dumps(event, separators=(",", ":")))

    async def _send_audio(self, websocket: ServerConnection, response_id: str, index: int) -> None:
        pcm = (index.to_bytes(2, "little", signed=False) * 160) if index < 65_536 else b"\x00" * 320
        await self._send(
            websocket,
            {
                "type": "response.output_audio.delta",
                "response_id": response_id,
                "delta": base64.b64encode(pcm).decode("ascii"),
            },
        )


async def run_mock_server(config: MockConfig) -> None:
    server = MockRealtimeServer(config)
    async with serve(server.handler, config.host, config.port, max_size=8 * 1024 * 1024):
        print(f"mock realtime server listening on ws://{config.host}:{config.port}/v1/realtime")
        await asyncio.Future()
