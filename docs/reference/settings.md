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
| `READINESS_TIMEOUT_SECONDS` | no | `3` | API | Budget for each database check of `GET /ready`; a slower database reports `not-ready`. The `SELECT 1` runs first, then the revision and model checks together under the same budget, so the probe answers within about twice this value. |
| `ENABLED_MODELS` | no | `clip-vit-l14` | API, CLI | Comma-separated model keys the service may use. Only keys this build has an adapter for are accepted; anything else refuses at start, naming the offender. |
| `MODEL_WARMUP` | no | empty | API | Comma-separated keys loaded at start, on the inference pool. Must be a subset of `ENABLED_MODELS`. Empty means a model is loaded on its first use. |
| `MODEL_CACHE` | no | `.data/models` | API, CLI | Directory the weights are cached in; about 1.6 GB for CLIP. Gitignored, and mountable into a container. |
| `CLIP_MODEL_NAME` | no | `openai/clip-vit-large-patch14` | API, CLI | The checkpoint behind the `clip-vit-l14` key. A mirror or compatible fine-tune may be substituted; one of another width is refused at load. |
| `TORCH_NUM_THREADS` | no | `0` | API, CLI | Threads for one forward pass. `0` leaves torch its own default; set it to the CPU quota in a container. |
| `EMBED_BATCH_SIZE` | no | `8` | API, CLI | Inputs per forward pass. Memory, not speed, sets this: a batch is one tensor. |
| `INFERENCE_WORKERS` | no | `2` | API | Threads that load models and run inference, away from the event loop. |

Template lines for the environment file (the template is `.env.example`,
copied to `.env` on first run):

```dotenv
DATABASE_URL=postgresql+asyncpg://<DB_USER>:<DB_PASSWORD>@127.0.0.1:5433/<DB_NAME>
LOG_LEVEL=info
LOG_JSON=false
READINESS_TIMEOUT_SECONDS=3
ENABLED_MODELS=clip-vit-l14
MODEL_WARMUP=
MODEL_CACHE=.data/models
CLIP_MODEL_NAME=openai/clip-vit-large-patch14
TORCH_NUM_THREADS=0
EMBED_BATCH_SIZE=8
INFERENCE_WORKERS=2
```

What the model settings mean in practice — the download, warm-up and
running offline — is in
[`../how-to/models.md`](../how-to/models.md).

`<DB_USER>`, `<DB_PASSWORD>` and `<DB_NAME>` are the values of the
Compose variables in the same file. `APP_PORT` is read by `make run` only
(default `8000`).
