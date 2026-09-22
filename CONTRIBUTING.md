# Contributing

Thanks for helping make voice-agent performance easier to measure.

For a bug, include the smallest scenario that reproduces it, the command, Python version, target implementation and version, and redacted `summary.json` plus relevant JSONL events. Do not attach user audio or transcripts without consent.

Discuss changes to the scenario schema, metric definitions, or protocol adapter in an issue first. These are public contracts. A metric change needs a definition, test vectors, and a note about whether old and new results can be compared.

Set up and validate a change with:

```bash
uv sync --all-extras --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov --cov-report=term-missing
```

Keep pull requests small. Add a unit test for parsing or math, and an end-to-end test against the mock target for session or protocol behavior. Never commit API keys, private audio, transcripts, or generated benchmark artifacts.
