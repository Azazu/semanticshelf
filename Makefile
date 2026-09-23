# Command interface for local development. Python runs via uv on the
# host; the database runs in Docker.
COMPOSE ?= docker compose
RUN     ?= uv run
MSG     ?= change

.DEFAULT_GOAL := help
.PHONY: help init up down ps logs run migrate revision test test-models test-integration demo lock-check lint fmt fmt-check types check

# Application targets are guarded until the scaffold exists: the change that
# adds the FastAPI app brings alembic.ini together with app/main.py. A
# Make-level conditional makes each guarded recipe either the single SKIP
# line or the real command, never both. `check` is deliberately unguarded:
# it is the gate floor and runs for real from the first change on.
ifeq ($(wildcard alembic.ini),)
APP_MISSING := 1
endif
SKIP_MSG = [SKIP] no alembic.ini — application not scaffolded yet

help: ## List available commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

init: ## First run: sync the environment, create the media root, start the database, migrate
	uv sync
	mkdir -p $${MEDIA_ROOT:-.data/media}
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
ifdef APP_MISSING
	@echo "$(SKIP_MSG)"
else
	$(RUN) uvicorn --factory app.main:create_app --reload --host 127.0.0.1 --port $${APP_PORT:-8000}
endif

migrate: ## Apply migrations
ifdef APP_MISSING
	@echo "$(SKIP_MSG)"
else
	$(RUN) alembic upgrade head
endif

revision: ## Autogenerate a migration: make revision MSG='add embeddings'
ifdef APP_MISSING
	@echo "$(SKIP_MSG)"
else
	$(RUN) alembic revision --autogenerate -m "$(MSG)"
endif

test: ## Unit and api tests (fake embedder, no database, no weights)
	$(RUN) pytest -m "not integration and not models"

test-models: ## Real-model smoke tests (downloads weights; on demand, never in CI)
	$(RUN) pytest -m models

test-integration: ## Integration tests (need the pgvector container)
ifdef APP_MISSING
	@echo "$(SKIP_MSG)"
else
	$(RUN) pytest -m integration
endif

lock-check: ## uv.lock matches pyproject.toml (CI syncs with --frozen, which does not check this)
	uv lock --check

lint: ## ruff check
	$(RUN) ruff check .

fmt: ## ruff format (writes)
	$(RUN) ruff format .

fmt-check: ## ruff format --check
	$(RUN) ruff format --check .

types: ## mypy on app/
	$(RUN) mypy app

demo: ## Fetch the demo corpus and index it, so a search has something to find
ifdef APP_MISSING
	@echo "$(SKIP_MSG)"
else
	$(RUN) semanticshelf demo-dataset download --count $${DEMO_COUNT:-500} --into $${DEMO_ROOT:-.data/demo}
	$(RUN) semanticshelf demo-dataset index --into $${DEMO_ROOT:-.data/demo}
endif

check: lock-check lint fmt-check types test ## The gate floor: lock + lint + format + types + tests
	@echo "check: all green"
