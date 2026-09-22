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
| `MEDIA_ROOT` | no | `.data/media` | API, CLI | Where an asset's bytes live: `<root>/<two hex characters of the id>/<id>.<ext>` and the thumbnail beside it. Outside any directory served by path, and never created by the service — `make init` creates it and `GET /ready` reports it when it is missing. |
| `MAX_UPLOAD_BYTES` | no | `20971520` (20 MiB) | API | The bound on a whole request body, counted as it arrives. It is the only bound on an uploaded file's size, so a deployment that wants larger pictures raises this one. |
| `MAX_IMAGE_PIXELS` | no | `40000000` | API | Width × height, refused above this from the picture's header before a pixel is allocated. |
| `MIN_IMAGE_SIDE` | no | `32` | API | The shorter side a picture must have to be worth indexing. |
| `PRUNE_MIN_AGE_SECONDS` | no | `3600` | CLI | `storage prune` ignores files younger than this. A margin, not the guarantee: an upload in flight is protected by an advisory lock. |
| `HNSW_EF_SEARCH` | no | `40` | API | How hard the vector index looks for each search. Every search raises it for its own transaction to at least the depth the page asks for, plus the one row that answers `has_more` (`limit + offset + 1`), so a deep page is not quietly ranked worse than a shallow one. 1000 is pgvector's own maximum, and one scan yields no more rows than that, so the deepest page the service answers ends at `limit + offset` = 999. |
| `JOB_LEASE_SECONDS` | no | `600` | API, worker | How long a claim on an indexing job is good for. Nothing refreshes it: a runner that dies releases its work when this expires, and another may then claim it. Raise it for a model slow enough that work would otherwise outlive the lease. |
| `JOB_MAX_ATTEMPTS` | no | `3` | API, worker | How many attempts a job gets before it is `failed` for good. Between attempts it waits `2^attempts × 10 s`. A `failed` job runs again only through `POST /assets/{id}/reindex`. |
| `WORKER_BATCH_SIZE` | no | `4` | API, worker | How many jobs one run of a runner claims. The runner inside the API process takes at most this many after a response and stops; a runner that drained while work remained would never end. |

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
MEDIA_ROOT=.data/media
MAX_UPLOAD_BYTES=20971520
MAX_IMAGE_PIXELS=40000000
MIN_IMAGE_SIDE=32
PRUNE_MIN_AGE_SECONDS=3600
JOB_LEASE_SECONDS=600
JOB_MAX_ATTEMPTS=3
WORKER_BATCH_SIZE=4
HNSW_EF_SEARCH=40
```

What the model settings mean in practice — the download, warm-up and
running offline — is in [`../how-to/models.md`](../how-to/models.md); what the
media settings mean when a picture arrives is in
[`../how-to/uploading.md`](../how-to/uploading.md); what the indexing
settings mean once it is stored is in
[`../how-to/indexing.md`](../how-to/indexing.md); what the search setting means
when a query arrives is in [`../how-to/searching.md`](../how-to/searching.md).

`<DB_USER>`, `<DB_PASSWORD>` and `<DB_NAME>` are the values of the
Compose variables in the same file. `APP_PORT` is read by `make run` only
(default `8000`).
