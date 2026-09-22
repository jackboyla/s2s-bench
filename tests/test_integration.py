from __future__ import annotations

from websockets.asyncio.server import serve

from s2s_bench.mock_server import MockConfig, MockRealtimeServer
from s2s_bench.models import AudioSpec, LoadConfig, Scenario, TurnSpec
from s2s_bench.runner import run_scenario, safe_target_url


async def test_end_to_end_normal_and_cancelled_turns() -> None:
    mock = MockRealtimeServer(MockConfig(stt_ms=5, llm_ms=5, tts_ms=5))
    async with serve(mock.handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        scenario = Scenario(
            name="integration",
            url=f"ws://127.0.0.1:{port}/v1/realtime",
            turns=(
                TurnSpec("normal", AudioSpec("synthetic:220:40", chunk_ms=10), settle_ms=10),
                TurnSpec(
                    "cancel",
                    AudioSpec("synthetic:330:40", chunk_ms=10),
                    cancel_after_first_audio_ms=0,
                    settle_ms=10,
                ),
            ),
            load=LoadConfig(sessions=2, concurrency=2),
            timeout_s=2,
        )
        result = await run_scenario(scenario)

    assert len(result.turns) == 4
    assert all(turn.status == "ok" for turn in result.turns)
    assert all("e2e_first_audio" in turn.metrics_ms for turn in result.turns)
    cancelled = [turn for turn in result.turns if turn.turn_name == "cancel"]
    assert all("cancellation" in turn.metrics_ms for turn in cancelled)


async def test_server_failure_is_reported() -> None:
    mock = MockRealtimeServer(MockConfig(stt_ms=1, fail_every=1))
    async with serve(mock.handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        scenario = Scenario(
            name="failure",
            url=f"ws://127.0.0.1:{port}",
            turns=(TurnSpec("turn", AudioSpec("synthetic:220:20", chunk_ms=10), settle_ms=0),),
            timeout_s=1,
        )
        result = await run_scenario(scenario)
    assert result.turns[0].status == "failed"
    assert "expected_completed" in result.turns[0].protocol_violations[0]


async def test_connection_failure_becomes_turn_data() -> None:
    scenario = Scenario(
        name="offline",
        url="ws://127.0.0.1:1/v1/realtime",
        turns=(TurnSpec("turn", AudioSpec("synthetic:220:20")),),
        timeout_s=0.1,
    )
    result = await run_scenario(scenario)
    assert result.turns[0].status == "failed"
    assert "session setup failed" in result.turns[0].errors[0]


def test_target_url_redacts_query_and_credentials() -> None:
    assert (
        safe_target_url("wss://user:secret@example.com:443/path?token=bad")
        == "wss://example.com:443/path"
    )
