# Settings

Every variable the service reads, from the environment or from a `.env`
file next to `pyproject.toml` (the environment wins). Source of truth:
`app/core/settings.py`. Compose-only variables (`DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `FORWARD_DB_PORT`, `BIND_ADDRESS`) live in
`docker-compose.yml` and are not read by the application.

| Variable | Required | Default | Read by | Meaning |
|---|---|---|---|---|
| `DATABASE_URL` | yes | — | API, Alembic, integration tests | SQLAlchemy URL with the `postgresql+asyncpg://` scheme. Locally it points at the published host port of the Compose database (`127.0.0.1:5433` by default), not at `5432`. |
| `LOG_LEVEL` | no | `info` | API | `debug`, `info`, `warning` or `error`; applies to the application and to the uvicorn / SQLAlchemy loggers. |
| `LOG_JSON` | no | `true` | API | `true`: one JSON object per log line on stdout. `false`: a coloured console renderer for local development. |
| `READINESS_TIMEOUT_SECONDS` | no | `3` | API | Budget for the `SELECT 1` of `GET /ready`; a slower database reports `not-ready`. |

Template lines for the environment file (the template is `.env.example`,
copied to `.env` on first run):

```dotenv
DATABASE_URL=postgresql+asyncpg://<DB_USER>:<DB_PASSWORD>@127.0.0.1:5433/<DB_NAME>
LOG_LEVEL=info
LOG_JSON=false
READINESS_TIMEOUT_SECONDS=3
```

`<DB_USER>`, `<DB_PASSWORD>` and `<DB_NAME>` are the values of the
Compose variables in the same file. `APP_PORT` is read by `make run` only
(default `8000`).
