# Command interface for local development. Python runs via uv on the
# host; the database runs in Docker.
COMPOSE ?= docker compose
RUN     ?= uv run
MSG     ?= change

.DEFAULT_GOAL := help
.PHONY: help init up down ps logs run migrate revision test test-integration lint fmt fmt-check types check

help: ## List available commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

init: ## First run: sync the environment, start the database, migrate
	uv sync
	$(COMPOSE) up -d db
	$(MAKE) migrate

up: ## Start the database (idempotent)
	$(COMPOSE) up -d db

down: ## Stop containers (data volume preserved)
	$(COMPOSE) down

ps: ## Container status
	$(COMPOSE) ps

logs: ## Tail database logs
	$(COMPOSE) logs --tail=100 -f db

run: ## Development server with reload
	$(RUN) uvicorn app.main:app --reload --host 127.0.0.1 --port $${APP_PORT:-8000}

migrate: ## Apply migrations
	$(RUN) alembic upgrade head

revision: ## Autogenerate a migration: make revision MSG='add embeddings'
	$(RUN) alembic revision --autogenerate -m "$(MSG)"

test: ## Unit tests (fake embedder, no database)
	$(RUN) pytest -m "not integration"

test-integration: ## Integration tests (need the pgvector container)
	$(RUN) pytest -m integration

lint: ## ruff check
	$(RUN) ruff check .

fmt: ## ruff format (writes)
	$(RUN) ruff format .

fmt-check: ## ruff format --check
	$(RUN) ruff format --check .

types: ## mypy on app/
	$(RUN) mypy app

check: lint fmt-check types test ## The gate floor: lint + format + types + tests
	@echo "check: all green"
