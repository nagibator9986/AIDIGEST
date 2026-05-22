.DEFAULT_GOAL := help
.PHONY: help install run migrate revision downgrade test lint fmt typecheck check \
        ingest score digest docker-up docker-down docker-logs clean

PYTHON ?= python3
VENV   ?= .venv
BIN     = $(VENV)/bin

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

install:  ## Create venv and install project with dev extras
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"

run:  ## Run the bot (polling + scheduler)
	$(BIN)/python -m app

migrate:  ## Apply all database migrations
	$(BIN)/python -m alembic upgrade head

revision:  ## Autogenerate a migration: make revision m="message"
	$(BIN)/python -m alembic revision --autogenerate -m "$(m)"

downgrade:  ## Roll back the last migration
	$(BIN)/python -m alembic downgrade -1

ingest:  ## Run one ingestion cycle manually
	$(BIN)/python -m app.cli ingest

score:  ## Run one scoring cycle manually
	$(BIN)/python -m app.cli score

digest:  ## Build and broadcast the digest now
	$(BIN)/python -m app.cli digest

test:  ## Run the test suite with coverage
	$(BIN)/pytest

lint:  ## Lint with ruff
	$(BIN)/ruff check app tests

fmt:  ## Auto-format with ruff
	$(BIN)/ruff format app tests
	$(BIN)/ruff check --fix app tests

typecheck:  ## Static type-check with mypy
	$(BIN)/mypy app

check: lint typecheck test  ## Run lint + typecheck + tests

docker-up:  ## Build and start the full stack
	docker compose up -d --build

docker-down:  ## Stop the stack
	docker compose down

docker-logs:  ## Tail the bot logs
	docker compose logs -f bot

clean:  ## Remove caches and build artefacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
