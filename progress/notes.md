# Notes

## Design research

- LiveKit correlates end-of-utterance, LLM TTFT, and TTS TTFB by turn and recommends checked-in scenarios for repeatable tests.
- Pipecat exposes first-byte and user-to-bot latency as distinct measures.
- Locust uses code-defined concurrent users and CI-friendly threshold reporting, but its core does not model a stateful voice turn.
- OpenTelemetry recommends low-cardinality operation names and explicit network attributes.
- Hugging Face `speech-to-speech` exposes the event boundaries needed for black-box measures over one WebSocket connection.
