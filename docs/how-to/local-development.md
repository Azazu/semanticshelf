# How to run SemanticShelf locally

Prerequisites: [uv](https://docs.astral.sh/uv/) (it downloads Python
3.12 itself on the first `make init`, one-time network access), Docker
with Compose v2, `make`, Node 22 (for the OpenSpec CLI:
`npm install -g @fission-ai/openspec`).

## First run

```bash
cp .env.example .env          # adjust FORWARD_DB_PORT if 5433 is taken
make init                     # uv sync, start pgvector, alembic upgrade head
make run                      # http://127.0.0.1:8000/api/docs
```

The variables the application reads are listed in
[`../reference/settings.md`](../reference/settings.md); `DATABASE_URL`
is the only required one. `make run` starts uvicorn with
`--factory app.main:create_app`, so the settings are read when the app is
built, not when the module is imported.

What to look at once it runs:

- `http://127.0.0.1:8000/health` — liveness: `{"status":"ok","version":…}`,
  touches nothing.
- `http://127.0.0.1:8000/ready` — readiness: 200 when the database
  answers within `READINESS_TIMEOUT_SECONDS` and its Alembic revision is
  the code's head, otherwise 503 with a reason per failed check. Docker
  healthchecks use this one.
- `http://127.0.0.1:8000/api/docs` — Swagger UI; the document itself is
  at `/api/openapi.json`.

Every error is an RFC 9457 problem-details body, every response carries
`X-Request-ID` (yours if you send one, generated otherwise), and every log
line written for a request carries the same id.

The baseline migration runs `CREATE EXTENSION IF NOT EXISTS vector`, which
needs the database owner role; the Compose database and the CI service
both run as that role.

Model weights download on first use into `MODEL_CACHE` (gitignored);
unit tests never need them.

## Daily

| Task | Command |
|---|---|
| database up / down | `make up` / `make down` |
| dev server | `make run` |
| migrations | `make migrate`, `make revision MSG='…'` |
| the gate floor | `make check` (lock check + ruff + mypy + unit and api tests, no database) |
| integration tests | `make test-integration` (needs the migrated container and `DATABASE_URL`) |

## Reset (DESTRUCTIVE)

`docker compose down --volumes` deletes the PostgreSQL volume. There is
no make target for it on purpose — type it yourself.

## Troubleshooting

- **`asyncpg` cannot connect** — `DATABASE_URL` in `.env` must use the
  host port (`5433` by default), not `5432`.
- **Slow first request** — the model is loading lazily; check
  `MODEL_CACHE` and available RAM (CLIP ViT-L/14 needs ~2 GB).
- **`make check` fails at `lock-check`** — `pyproject.toml` changed
  without `uv lock`. Run `uv lock` and commit `uv.lock`. CI syncs with
  `uv sync --frozen`, which uses the lock as-is and would not notice;
  the check inside `make check` is what catches it there too.
