from __future__ import annotations

import asyncio
import json
import platform
import random
import socket
import sys
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from websockets.asyncio.client import connect

from .audio import chunks, load_pcm16
from .models import EventRecord, RunResult, Scenario, TurnResult, TurnSpec
from .protocol import (
    AUDIO_DELTA_TYPES,
    RESPONSE_CREATED,
    RESPONSE_DONE,
    SPEECH_STARTED,
    SPEECH_STOPPED,
    TEXT_DELTA_TYPES,
    TRANSCRIPT_DONE,
    audio_append,
    public_event,
    response_status,
)

Clock = Callable[[], int]


class RealtimeSession:
    def __init__(
        self,
        websocket: Any,
        session_id: str,
        run_start_ns: int,
        timeout_s: float,
        clock: Clock = time.perf_counter_ns,
    ) -> None:
        self.websocket = websocket
        self.session_id = session_id
        self.run_start_ns = run_start_ns
        self.timeout_s = timeout_s
        self.clock = clock
        self.inbox: asyncio.Queue[tuple[int, dict[str, Any]]] = asyncio.Queue()
        self.all_events: list[EventRecord] = []
        self.current_turn_id: str | None = None
        self.receiver: asyncio.Task[None] | None = None

    async def start(self, session_config: dict[str, Any]) -> None:
        self.receiver = asyncio.create_task(self._receive(), name=f"receive-{self.session_id}")
        created = await self.next_event(lambda event: event.get("type") == "session.created")
        if created.get("type") != "session.created":  # pragma: no cover - predicate is explicit
            raise RuntimeError("server did not create a session")
        await self.send({"type": "session.update", "session": session_config})
        await self.next_event(lambda event: event.get("type") in {"session.updated", "error"})

    async def close(self) -> None:
        if self.receiver is not None:
            self.receiver.cancel()
            await asyncio.gather(self.receiver, return_exceptions=True)

    async def _receive(self) -> None:
        async for raw in self.websocket:
            received_ns = self.clock()
            if not isinstance(raw, str):
                continue
            event = json.loads(raw)
            if not isinstance(event, dict):
                continue
            record = EventRecord(
                session_id=self.session_id,
                turn_id=self.current_turn_id,
                direction="received",
                event_type=str(event.get("type", "unknown")),
                monotonic_ns=received_ns,
                elapsed_ms=(received_ns - self.run_start_ns) / 1_000_000,
                data=public_event(event),
            )
            self.all_events.append(record)
            await self.inbox.put((received_ns, event))

    async def send(self, event: dict[str, Any]) -> int:
        sent_ns = self.clock()
        await self.websocket.send(json.dumps(event, separators=(",", ":")))
        self.all_events.append(
            EventRecord(
                session_id=self.session_id,
                turn_id=self.current_turn_id,
                direction="sent",
                event_type=str(event.get("type", "unknown")),
                monotonic_ns=sent_ns,
                elapsed_ms=(sent_ns - self.run_start_ns) / 1_000_000,
                data=public_event(event),
            )
        )
        return sent_ns

    async def next_event(self, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        async with asyncio.timeout(self.timeout_s):
            while True:
                _, event = await self.inbox.get()
                if predicate(event):
                    return event

    async def run_turn(
        self, spec: TurnSpec, index: int, rng: random.Random, scenario: Scenario
    ) -> TurnResult:
        turn_id = f"{self.session_id}-t{index + 1}"
        self.current_turn_id = turn_id
        event_start = len(self.all_events)
        anchors: dict[str, int] = {}
        errors: list[str] = []
        violations: list[str] = []
        final_status: str | None = None
        first_audio_seen = False
        cancellation_sent = False

        try:
            pcm = load_pcm16(spec.audio)
            audio_chunks = chunks(pcm, spec.audio.sample_rate, spec.audio.chunk_ms)
            anchors["input_start"] = self.clock()
            last_send_ns: int | None = None
            for chunk in audio_chunks:
                if (
                    scenario.faults.drop_audio_probability
                    and rng.random() < scenario.faults.drop_audio_probability
                ):
                    continue
                if scenario.faults.send_jitter_ms:
                    delay_ms = rng.uniform(0, scenario.faults.send_jitter_ms)
                    await asyncio.sleep(delay_ms / 1000)
                last_send_ns = await self.send(audio_append(chunk))
                if spec.audio.pace:
                    await asyncio.sleep(spec.audio.chunk_ms / 1000)
            anchors["input_end"] = last_send_ns or self.clock()

            async with asyncio.timeout(scenario.timeout_s):
                while True:
                    received_ns, event = await self.inbox.get()
                    event_type = str(event.get("type", "unknown"))
                    if event_type == SPEECH_STARTED:
                        anchors.setdefault("speech_started", received_ns)
                    elif event_type == SPEECH_STOPPED:
                        anchors.setdefault("speech_stopped", received_ns)
                    elif event_type == TRANSCRIPT_DONE:
                        anchors.setdefault("transcript_done", received_ns)
                    elif event_type == RESPONSE_CREATED:
                        anchors.setdefault("response_created", received_ns)
                    elif event_type in TEXT_DELTA_TYPES:
                        anchors.setdefault("first_text", received_ns)
                    elif event_type in AUDIO_DELTA_TYPES:
                        anchors.setdefault("first_audio", received_ns)
                        first_audio_seen = True
                        if "response_created" not in anchors:
                            violations.append("audio_before_response_created")
                    elif event_type == "error":
                        errors.append(str(event.get("error", event)))
                    elif event_type == RESPONSE_DONE:
                        anchors["response_done"] = received_ns
                        final_status = response_status(event) or "unknown"
                        break

                    if (
                        first_audio_seen
                        and spec.cancel_after_first_audio_ms is not None
                        and not cancellation_sent
                    ):
                        await asyncio.sleep(spec.cancel_after_first_audio_ms / 1000)
                        anchors["cancel_sent"] = await self.send({"type": "response.cancel"})
                        cancellation_sent = True
        except TimeoutError:
            errors.append(f"turn timed out after {scenario.timeout_s:g}s")
        except Exception as exc:  # session errors must become benchmark data
            errors.append(f"{type(exc).__name__}: {exc}")

        stale_events = 0
        terminal_ns = anchors.get("response_done")
        if terminal_ns is not None and spec.settle_ms > 0:
            deadline = asyncio.get_running_loop().time() + spec.settle_ms / 1000
            while (remaining := deadline - asyncio.get_running_loop().time()) > 0:
                try:
                    received_ns, event = await asyncio.wait_for(self.inbox.get(), timeout=remaining)
                except TimeoutError:
                    break
                if str(event.get("type")) in AUDIO_DELTA_TYPES and received_ns > terminal_ns:
                    stale_events += 1
                    violations.append("audio_after_response_done")

        metrics = derive_metrics(anchors)
        expected = "cancelled" if spec.cancel_after_first_audio_ms is not None else "completed"
        if final_status is not None and final_status != expected:
            violations.append(f"response_status_{final_status}_expected_{expected}")
        status = "ok" if not errors and not violations and final_status == expected else "failed"
        self.current_turn_id = None
        return TurnResult(
            session_id=self.session_id,
            turn_id=turn_id,
            turn_name=spec.name,
            status=status,
            metrics_ms=metrics,
            errors=errors,
            protocol_violations=violations,
            stale_events=stale_events,
            events=self.all_events[event_start:],
        )


def derive_metrics(anchors: dict[str, int]) -> dict[str, float]:
    pairs = {
        "vad_finalize": ("input_end", "speech_stopped"),
        "stt_final": ("speech_stopped", "transcript_done"),
        "llm_first_text": ("transcript_done", "first_text"),
        "tts_first_audio": ("first_text", "first_audio"),
        "e2e_first_audio": ("speech_stopped", "first_audio"),
        "response_complete": ("speech_stopped", "response_done"),
        "cancellation": ("cancel_sent", "response_done"),
    }
    metrics: dict[str, float] = {}
    for name, (start, end) in pairs.items():
        if start in anchors and end in anchors:
            metrics[name] = max(0.0, (anchors[end] - anchors[start]) / 1_000_000)
    return metrics


async def run_scenario(scenario: Scenario) -> RunResult:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    started_at = datetime.now(UTC).isoformat()
    run_start_ns = time.perf_counter_ns()
    semaphore = asyncio.Semaphore(scenario.load.concurrency)

    async def one_session(index: int) -> list[TurnResult]:
        if scenario.load.ramp_up_s and scenario.load.sessions > 1:
            await asyncio.sleep(index * scenario.load.ramp_up_s / (scenario.load.sessions - 1))
        async with semaphore:
            session_id = f"s{index + 1:04d}"
            rng = random.Random(scenario.faults.seed + index)
            try:
                async with connect(
                    scenario.url,
                    additional_headers=scenario.headers or None,
                    max_size=8 * 1024 * 1024,
                    open_timeout=scenario.timeout_s,
                    close_timeout=2,
                ) as websocket:
                    session = RealtimeSession(
                        websocket, session_id, run_start_ns, scenario.timeout_s
                    )
                    try:
                        await session.start(scenario.session)
                        return [
                            await session.run_turn(turn, turn_index, rng, scenario)
                            for turn_index, turn in enumerate(scenario.turns)
                        ]
                    finally:
                        await session.close()
            except Exception as exc:
                message = f"session setup failed: {type(exc).__name__}: {exc}"
                return [
                    TurnResult(
                        session_id=session_id,
                        turn_id=f"{session_id}-t{turn_index + 1}",
                        turn_name=turn.name,
                        status="failed",
                        errors=[message],
                    )
                    for turn_index, turn in enumerate(scenario.turns)
                ]

    nested = await asyncio.gather(*(one_session(index) for index in range(scenario.load.sessions)))
    turns = [turn for session_turns in nested for turn in session_turns]
    duration_s = (time.perf_counter_ns() - run_start_ns) / 1_000_000_000
    return RunResult(
        run_id=run_id,
        scenario=scenario.name,
        started_at=started_at,
        duration_s=duration_s,
        turns=turns,
        metadata={
            "target_url": safe_target_url(scenario.url),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "hostname": socket.gethostname(),
            "sessions": scenario.load.sessions,
            "concurrency": scenario.load.concurrency,
            "faults": {
                "send_jitter_ms": scenario.faults.send_jitter_ms,
                "drop_audio_probability": scenario.faults.drop_audio_probability,
                "seed": scenario.faults.seed,
            },
        },
    )


def safe_target_url(url: str) -> str:
    """Remove query parameters and credentials before a target reaches an artifact."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))
