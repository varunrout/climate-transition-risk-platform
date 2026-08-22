.PHONY: install lint format typecheck test test-cov check ingest run clean

install:
	uv sync --all-extras

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

test:
	uv run pytest

test-cov:
	uv run pytest --cov=climate_risk --cov-report=term-missing --cov-report=html

check: lint typecheck test

ingest:
	uv run climate-risk ingest

run:
	uv run climate-risk run

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage dist build
