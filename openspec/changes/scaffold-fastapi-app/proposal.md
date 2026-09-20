# Proposal — scaffold-fastapi-app

**Risk-Tier:** medium

Tier rationale: an ordinary application scaffold (endpoints, settings, logging, database wiring, a baseline migration that only creates the pgvector extension). No upload, deletion, concurrency, model download or CI edit; the Makefile guard becomes inert by construction when `alembic.ini` appears, which is the behaviour change 1 designed and tested.

## Why

The tooling floor exists (change 1) but there is no application: `make run` and `make migrate` still print SKIP, and every feature change from the schema onward needs an app factory, settings, a database engine, migrations, the error format and the test layers to build on. This change delivers that skeleton with the two probes and the HTTP conventions the specification fixes (§2.10, §4), so later changes add behaviour instead of infrastructure.

## What Changes

1. **Application factory and lifespan** (`app/main.py`): `create_app(settings)` builds the FastAPI instance with `/api/docs` and `/api/openapi.json` (ReDoc off), title and version from the package, the routers, the middleware and the exception handlers; the lifespan creates the async engine and disposes it on shutdown. `uvicorn app.main:app` keeps working through a module-level `app = create_app()`.
2. **Settings** (`app/core/settings.py`): pydantic-settings, environment and `.env`; `DATABASE_URL` (required, must be `postgresql+asyncpg://`), `LOG_LEVEL` (default `info`), `LOG_JSON` (default `true`), `READINESS_TIMEOUT_SECONDS` (default `3`). Loaded lazily by the factory, never at import time, so `make check` needs no database variables.
3. **Structured logging and request id** (`app/core/logging.py`, `app/core/request_id.py`): structlog JSON lines on stdout (console renderer when `LOG_JSON=false`), stdlib loggers (uvicorn, sqlalchemy) routed through the same renderer; an ASGI middleware that honours or generates `X-Request-ID`, binds it into structlog context for the request and returns it in the response.
4. **Problem details** (`app/core/errors.py`): every non-2xx is RFC 9457 `application/problem+json` with `type`, `title`, `status`, `detail`, `instance` (`urn:request:<request-id>`); validation errors are 422 with `errors[]` of `{loc, msg, type}` (never `input` or `ctx`); unhandled exceptions are 500 without any detail, logged once with the request id and the traceback; nothing from the exception reaches the client.
5. **Database wiring** (`app/db/engine.py`, `app/db/base.py`): async engine factory (`asyncpg`, `pool_pre_ping`), `async_sessionmaker`, a `get_session` FastAPI dependency reading the engine from `app.state`, the SQLAlchemy `DeclarativeBase` with naming conventions for constraints.
6. **Alembic baseline** (`alembic.ini`, `alembic/`): async environment reading `DATABASE_URL` from settings (never written into the ini), revision `0001_baseline` that runs `CREATE EXTENSION IF NOT EXISTS vector` and is reversible. Creating `alembic.ini` makes the Makefile guard inert: `make migrate`, `make run`, `make revision`, `make test-integration` are real from this change on.
7. **Probes** (`app/api/health.py`): `GET /health` (liveness, no dependencies) and `GET /ready` (readiness: `SELECT 1` within the timeout, migration head applied); both outside `/api/v1` and documented in OpenAPI.
8. **Test layers**: `tests/api/` (httpx `AsyncClient` over `ASGITransport` against `create_app()` with test settings, no database), `tests/integration/` (`-m integration`, real pgvector database, migrated by `make migrate` beforehand); shared fixtures in `tests/conftest.py`. The fake-embedder fixture named by the roadmap row arrives with the `Embedder` protocol in change 4 — nothing to inject exists before that; the conftest layout is prepared for it.
9. **Dependencies** (runtime group): `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `structlog`; dev: `httpx`. All named by the specification §5 with their justification; versions pinned by `uv.lock`.
10. **Docs**: `docs/reference/settings.md` (every variable, default, who reads it — the source for the environment template), `docs/how-to/local-development.md` (the SKIP section retired, the three URLs, the readiness semantics), `docs/reference/commands.md` (guard note updated), `README.md` (stage line, quick start URLs).

## Capabilities

### New Capabilities

- `health-probes`: liveness and readiness endpoints, their response shapes, the checks readiness performs and how it reports failures.
- `http-api-conventions`: the request id contract, the RFC 9457 problem-details error format for every non-2xx response, and where the OpenAPI document and Swagger UI live.

### Modified Capabilities

None (there are no main specs yet).

## Non-goals

- No domain tables, repositories or models: `assets`, `embeddings`, `indexing_jobs` are `add-assets-and-embeddings-schema` (change 3); the baseline migration creates only the extension.
- No `Embedder`, registry, fake embedder or model settings (change 4). The readiness check for embedder dimensions (FR-MDL-7) is added by that change.
- No `MEDIA_ROOT` and no storage checks in readiness (change 5). No `/api/v1/stats` (change 8).
- No migration down/up round trip in CI (change 3, together with the first real schema).
- No authentication, rate limiting, CORS (the UI talks to the API server-side; a browser client is a non-goal of the specification).
- No edit to `.github/workflows/ci.yml`: the existing `python` job already migrates and runs the integration marker with `DATABASE_URL`.
- No edit to the environment template by the executor (policy tooling blocks `.env*`): `docs/reference/settings.md` is the source, and the user aligns the template from it (task 6.2).

## Impact

- New: `app/main.py`, `app/core/{settings,logging,request_id,errors}.py`, `app/api/{__init__,health}.py`, `app/db/{__init__,engine,base}.py`, `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_baseline.py`, `tests/conftest.py`, `tests/api/`, `tests/integration/`, `docs/reference/settings.md`.
- Modified: `pyproject.toml` (runtime dependencies, dev `httpx`, `asyncio_mode` stays `auto`, `integration` marker already registered), `uv.lock`, `docs/how-to/local-development.md`, `docs/reference/commands.md`, `README.md`, `docs/README.md` (reference index).
- `Makefile`: unchanged; its guard turns inert because `alembic.ini` now exists (verified by task 5.3).
- New runtime dependencies, each against the anti-overengineering rule: `fastapi` + `uvicorn[standard]` (the HTTP framework and server the specification fixes), `pydantic-settings` (settings from the environment, the only sanctioned source), `sqlalchemy[asyncio]` + `asyncpg` (typed async ORM and the standard async PostgreSQL driver), `alembic` (reviewed migrations), `structlog` (bound request context across the threadpool and the worker; the stdlib has no bound context). Dev: `httpx` (FastAPI's own test transport). `pydantic` is a transitive dependency of FastAPI and is declared explicitly because the code imports it directly.
