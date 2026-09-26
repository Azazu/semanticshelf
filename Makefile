# Command interface for local development. Python runs via uv on the
# host; the database runs in Docker.
COMPOSE ?= docker compose
RUN     ?= uv run
MSG     ?= change

.DEFAULT_GOAL := help
.PHONY: help init up down ps logs run migrate revision test test-models test-integration ui test-ui screenshots demo lock-check lint fmt fmt-check types check image stack stack-down stack-logs stack-warm sca-image

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
	$(RUN) pytest -m "not integration and not models and not ui"

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

ui: ## Run the Streamlit demo (needs the `ui` group: uv sync --group ui)
ifdef APP_MISSING
	@echo "$(SKIP_MSG)"
else
	@echo "the demo is at http://127.0.0.1:$${UI_PORT:-8501} — the service must be running ($(MAKE) run)"
	uv run --group ui streamlit run ui/app.py --server.port $${UI_PORT:-8501} --server.headless true --browser.gatherUsageStats false
endif

test-ui: ## Smoke tests of the demo pages against a stubbed API (needs the `ui` group)
ifdef APP_MISSING
	@echo "$(SKIP_MSG)"
else
	uv run --group ui pytest -m ui
endif

screenshots: ## Capture the README screenshots (needs the `ui` and `screenshots` groups)
ifdef APP_MISSING
	@echo "$(SKIP_MSG)"
else
	uv run --group ui --group screenshots python scripts/screenshots.py
endif

demo: ## Fetch the demo corpus and index it, so a search has something to find
ifdef APP_MISSING
	@echo "$(SKIP_MSG)"
else
	$(RUN) semanticshelf demo-dataset download --count $${DEMO_COUNT:-500} --into $${DEMO_ROOT:-.data/demo}
	$(RUN) semanticshelf demo-dataset index --into $${DEMO_ROOT:-.data/demo}
	$(RUN) semanticshelf index missing
endif

check: lock-check lint fmt-check types test ## The gate floor: lock + lint + format + types + tests
	@echo "check: all green"

# --- the container stack --------------------------------------------------------

STACK_IMAGE ?= semanticshelf
# Pinned: a scanner that moves under you reports different things about the same
# image, and "it passed last week" stops meaning anything. Bump deliberately.
TRIVY_IMAGE ?= ghcr.io/aquasecurity/trivy:0.69.0

image: ## Build both images: the service and the demo interface
	docker build --target runtime -t $(STACK_IMAGE):runtime .
	docker build --target ui -t $(STACK_IMAGE):ui .

stack: ## Start the whole system in containers (writes the local env file on first run)
	sh scripts/stack-env.sh
	$(COMPOSE) up -d --wait
	@echo "api:  http://$${BIND_ADDRESS:-127.0.0.1}:$${APP_PORT:-8000}/api/docs"
	@echo "ui:   http://$${BIND_ADDRESS:-127.0.0.1}:$${UI_PORT:-8501}"

stack-down: ## Stop the stack; its volumes (media, weights, database) are kept
	$(COMPOSE) down

stack-logs: ## Follow the stack's logs
	$(COMPOSE) logs -f

stack-warm: ## Fill the model cache volume through the service image (one-shot)
	$(COMPOSE) run --rm --no-deps worker semanticshelf models warm

sca-image: ## Scan the service image: HIGH/CRITICAL findings that have a fix
	docker run --rm \
		-v /var/run/docker.sock:/var/run/docker.sock \
		-v semanticshelf_trivy:/root/.cache/trivy \
		$(TRIVY_IMAGE) image --scanners vuln \
		--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 \
		$(STACK_IMAGE):runtime
