# How to run SemanticShelf locally

Prerequisites: Python 3.12 via [uv](https://docs.astral.sh/uv/), Docker
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

## Daily

| Task | Command |
|---|---|
| database up / down | `make up` / `make down` |
| dev server | `make run` |
| migrations | `make migrate`, `make revision MSG='…'` |
| the gate floor | `make check` (ruff + mypy + unit tests) |
| integration tests | `make test-integration` (needs the container) |

## Reset (DESTRUCTIVE)

`docker compose down --volumes` deletes the PostgreSQL volume. There is
no make target for it on purpose — type it yourself.

## Troubleshooting

- **`asyncpg` cannot connect** — `DATABASE_URL` in `.env` must use the
  host port (`5433` by default), not `5432`.
- **Slow first request** — the model is loading lazily; check
  `MODEL_CACHE` and available RAM (CLIP ViT-L/14 needs ~2 GB).
- **`make check` differs from CI** — CI uses `uv sync --frozen`; run
  `uv lock` after changing dependencies and commit `uv.lock`.
