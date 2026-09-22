.PHONY: install check test smoke

install:
	uv sync --all-extras --dev

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

test:
	uv run pytest --cov --cov-report=term-missing

smoke:
	uv run s2s-bench run examples/mock-smoke.yaml --output artifacts/smoke
