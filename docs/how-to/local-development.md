# How to run SemanticShelf locally

Prerequisites: [uv](https://docs.astral.sh/uv/) (it downloads Python
3.12 itself on the first `make init`, one-time network access), Docker
with Compose v2, `make`, Node 22 (for the OpenSpec CLI:
`npm install -g @fission-ai/openspec`).

## First run

```bash
cp .env.example .env          # adjust FORWARD_DB_PORT if 5433 is taken
make init                     # uv sync, start pgvector, alembic upgrade head
make run                      # http://127.0.0.1:8000/docs
```

Model weights download on first use into `MODEL_CACHE` (gitignored);
unit tests never need them.

## Before the application exists

Until the FastAPI scaffold lands (it brings `alembic.ini` and
`app/main.py` together), `make migrate`, `make revision MSG='…'`,
`make run` and `make test-integration` print
`[SKIP] no alembic.ini — application not scaffolded yet` and exit 0, so
`make init` ends on that line after the database is healthy. `make check`
is real from the start: ruff, the format check, mypy strict and the unit
tests run against the package as it is.

## Daily

| Task | Command |
|---|---|
| database up / down | `make up` / `make down` |
| dev server | `make run` |
| migrations | `make migrate`, `make revision MSG='…'` |
| the gate floor | `make check` (lock check + ruff + mypy + unit tests) |
| integration tests | `make test-integration` (needs the container) |

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
