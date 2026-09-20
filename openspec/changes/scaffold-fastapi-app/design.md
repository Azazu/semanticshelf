# Design — scaffold-fastapi-app

## Context

See `proposal.md` — Why. Current state: an empty `app` package on the uv tooling of change 1; the Makefile guard on `alembic.ini`; CI migrates and runs `-m integration` with `DATABASE_URL` pointing at a pgvector service; `make check` runs without any database variable. Constraints: specification §2.10 (probes), §4 (problem details, request id, OpenAPI), §6.4 (structlog, request id in logs), `AGENTS.md` layout and the "settings only from the environment" rule; the executor cannot read or write `.env*` files.

## Goals / Non-Goals

**Goals:** a factory-built FastAPI app with lazy settings, the two probes, the error and request-id contract, the async engine and a reversible baseline migration, the api and integration test layers, and documentation of every setting.

**Non-Goals:** anything listed under Non-goals in the proposal; performance work; a worker process; any domain table.

## Decisions

1. **Factory with injected settings, no import-time side effects.** `create_app(settings: Settings | None = None)`; the module-level `app = create_app()` exists for `uvicorn app.main:app` and builds settings from the environment at import of `app.main` only. Tests call `create_app(Settings(database_url=..., log_json=False))`. `get_settings()` is not a global singleton read by modules at import; it is called by the factory. Rationale: `make check` in CI has no `DATABASE_URL`, and unit tests must construct apps with different settings in one process.
2. **Engine in the lifespan, on `app.state`.** The lifespan creates `create_async_engine(settings.database_url, pool_pre_ping=True)` and disposes it on shutdown; `get_session` (dependency) yields an `AsyncSession` from `async_sessionmaker(app.state.engine, expire_on_commit=False)`. No connection is opened at startup, so a booting API with a database still starting is `not-ready`, not crashed. Alternative rejected: a module-level engine created at import (untestable, import-time side effect).
3. **Request id as a pure ASGI middleware**, not `BaseHTTPMiddleware` (which buffers responses and breaks streaming for the file endpoints of change 5). It reads/validates `X-Request-ID`, generates a UUID4 otherwise, binds `request_id`, `method`, `path` into `structlog.contextvars`, and injects the header into the response start message. The validation regex `^[A-Za-z0-9._-]{1,128}$` keeps a client from injecting log-breaking or oversized values.
4. **Problem details through three exception handlers**: `RequestValidationError` → 422 `/errors/validation` with `errors[]` stripped to `loc`, `msg`, `type` (never `input`/`ctx`/`url`, which can echo bodies); `StarletteHTTPException` (covers FastAPI's `HTTPException`, 404 for unknown routes, 405) → `about:blank` with the exception's detail as `detail`; `Exception` → 500 `Internal Server Error`, empty `detail`, one `log.error` with `exc_info`. All bodies carry `instance = urn:request:<id>` read from the context var. A small `ProblemDetails` Pydantic model documents the schema and is referenced as the default error response in OpenAPI (`responses` on the app / routers). The 500 handler is registered on the app; under the ASGI test transport `raise_server_exceptions=False` is used to assert the 500 body.
5. **structlog configured once by the factory**: processors merge contextvars, add timestamp (ISO, UTC) and level, render JSON (`LOG_JSON=true`) or console; the stdlib root logger gets a `ProcessorFormatter` handler so uvicorn's and SQLAlchemy's records render identically; `LOG_LEVEL` applies to both. Uvicorn's access log is kept (it is useful) but rendered by the same formatter. Alternative rejected: stdlib JSON formatter (no bound context across threadpool calls, which the worker and inference paths need later).
6. **Readiness checks as small async functions** in `app/api/health.py`'s service module (`app/services/readiness.py`): `check_database(engine, timeout)` runs `SELECT 1` under `asyncio.wait_for`; `check_migrations(engine, script_location)` compares `MigrationContext.get_current_revision()` (via `connection.run_sync`) with `ScriptDirectory.get_current_head()`. Results are `{"ok": True} | {"ok": False, "reason": "<class>: <one line>"}`; the URL is never part of a reason (asyncpg messages do not include the password, but the reason is trimmed to the exception class and first line anyway). Timeouts report `TimeoutError`.
7. **Alembic with the classic `async` template and `alembic.ini`**, not the `pyproject` template: the Makefile guard and the docs key on `alembic.ini`. `env.py` takes the URL from `Settings` (never from the ini, so `%` in a password cannot break configparser) and runs migrations through the async engine. Revision ids are readable (`0001_baseline`); `file_template` in the ini enforces the `NNNN_slug` naming. The baseline creates the `vector` extension and its `downgrade` drops it (`DROP EXTENSION IF EXISTS vector`), which is reversible while no table uses the type.
8. **DeclarativeBase with naming conventions** (`ix_%(column_0_label)s`, `uq_%(table_name)s_%(column_0_name)s`, `ck_%(table_name)s_%(constraint_name)s`, `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`, `pk_%(table_name)s`) so change 3's autogenerate produces named constraints that `downgrade()` can drop.
9. **Test layers.** `tests/conftest.py`: `test_settings` fixture (a `DATABASE_URL` from the environment when present, else a syntactically valid unreachable URL on port 1 for api tests that never touch the database), `app` fixture (`create_app(test_settings)`), `client` fixture (`httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`; httpx's transport does not run the lifespan, so the fixture enters `app.router.lifespan_context(app)` itself — no extra dependency). Integration tests are marked and read `DATABASE_URL` from the environment or `.env` through `Settings`; they assume `make migrate` ran (CI does; locally the how-to says so) and skip with a clear message when `DATABASE_URL` is unset.
10. **Settings surface kept to what this change reads**: `DATABASE_URL`, `LOG_LEVEL`, `LOG_JSON`, `READINESS_TIMEOUT_SECONDS`. `docs/reference/settings.md` lists them and becomes the authority the user aligns the environment template with; every later change that adds a variable extends that page in the same commit as the code.

## Risks / Trade-offs

- [The environment template may lack `DATABASE_URL` or carry a different name; the executor cannot check] → `docs/reference/settings.md` states the exact lines; the user compares and applies (task 6.2); `make run` without the variable fails at the factory with a clear settings error naming `DATABASE_URL`.
- [`CREATE EXTENSION vector` needs privileges] → the pgvector image's default role owns the database and is a superuser; CI uses the same image; documented in the how-to.
- [Uvicorn access logs duplicate the request line] → kept, rendered through structlog with the request id absent (uvicorn logs after the middleware unbinds); acceptable for a scaffold, revisited if noisy.
- [The 500 handler cannot catch errors raised inside middleware] → the request-id middleware does no work that can fail beyond header parsing, which it guards.
- [Guard inertness]: `alembic.ini` appears → `make migrate`/`run`/`revision`/`test-integration` run for real; CI's integration step runs `make migrate` against the service and then the marked tests (task 5.3 verifies locally).

## Migration Plan

Apply on the branch; `make check` green; `make migrate && make test-integration` green locally against the Compose database; user pushes; CI green; Gate 2; merge. Rollback: revert the merge commit; `alembic downgrade base` drops the extension.

## Open Questions

None.
