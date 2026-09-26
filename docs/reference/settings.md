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
| `ENABLED_MODELS` | no | `clip-vit-l14,dinov2-large` | API, CLI | Comma-separated model keys the service may use. The default is every key this build implements, so an upload is queued for both and both kinds of search answer. Only keys this build has an adapter for are accepted; anything else refuses at start, naming the offender. A deployment that runs one model halves what an upload costs and gives up the search the other one answers — without `dinov2-large` a picture query and `GET /assets/{id}/similar` are 503. |
| `MODEL_WARMUP` | no | empty | API | Comma-separated keys loaded at start, on the inference pool. Must be a subset of `ENABLED_MODELS`. Empty means a model is loaded on its first use. |
| `MODEL_CACHE` | no | `.data/models` | API, CLI | Directory the weights are cached in: about 1.6 GB for CLIP and 1.2 GB for DINOv2, downloaded on first use. Gitignored, and mountable into a container. |
| `CLIP_MODEL_NAME` | no | `openai/clip-vit-large-patch14` | API, CLI | The checkpoint behind the `clip-vit-l14` key. A mirror or compatible fine-tune may be substituted; one of another width is refused at load. |
| `DINOV2_MODEL_NAME` | no | `facebook/dinov2-large` | API, CLI | The checkpoint behind the `dinov2-large` key, under the same rule. It has no text tower: asking it for words is refused rather than approximated. |
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
| `WORKER_BATCH_SIZE` | no | `4` | API, worker | How many jobs one run of a runner claims. The runner inside the API process takes at most this many after a response and stops; a runner that drained while work remained would never end. The worker keeps the same bound per batch, which is what lets several workers share a queue and what keeps a stop from waiting for an unbounded amount of work. |
| `WORKER_POLL_SECONDS` | no | `2` | worker | How long the worker waits before looking again when the queue held nothing for it. A floor on how late a vector can be, against a claim query in a loop; a stop does not wait it out, because the wait *is* the wait for the stop. |
| `ALEMBIC_DIR` | no | the `alembic/` beside the installed package | API | Where the migration scripts are. Only `GET /ready` reads it, to compare the database's revision with the code's head. The default is computed from the package's own location, which is right in a checkout and wrong once the package is installed into a virtual environment — there, one level up is `site-packages`, where `alembic` is the library and has no revisions. The container stack sets `/app/alembic`; a probe that cannot find them answers `code head none` rather than ready (change 15). |
| `API_BASE_URL` | no | `http://127.0.0.1:8000` | demo UI | The address the interface calls. |
| `API_PUBLIC_URL` | no | whatever `API_BASE_URL` is | demo UI | The address the interface gives a **browser** for the pictures the API links to. Separate because the two are not always the same network: in the container stack the interface calls `http://api:8000` and the browser on the host cannot resolve that name, so every thumbnail would be a broken image (change 15). A single-host run leaves it unset. |
| `INDEXING_RUNNER` | no | `inline` | API, worker, CLI | Which runner carries out queued work. `inline` is the runner inside whatever process created it — the API after a response, `index-folder` and `index missing` after their import — so a deployment nobody configured still indexes what it accepts. `worker` leaves all of it to `semanticshelf worker`: the API and the commands then queue the work and execute none of it, and a command that did so says which decided it. Set it to `worker` **and start one**, or nothing is ever indexed. |

The template itself is the environment example at the repository root — copy it
to the environment file on first run and edit what you need. It carries the
lines a local run has to be told (the database URL, the media root) and a few
worth seeing at a glance; every setting in the table above has a default, so a
line the template omits is a setting you have not had to think about yet.

This page used to repeat that file's contents. It stopped when the two were
found to disagree — nine lines the page showed were not in the file — which is
what a second copy of a repository file is always eventually for. One authority
each: the table above for what a setting means, the template for what a fresh
checkout starts with.

What the model settings mean in practice — the download, warm-up and
running offline — is in [`../how-to/models.md`](../how-to/models.md); what the
media settings mean when a picture arrives is in
[`../how-to/uploading.md`](../how-to/uploading.md); what the indexing
settings mean once it is stored is in
[`../how-to/indexing.md`](../how-to/indexing.md); what the search setting means
when a query arrives is in [`../how-to/searching.md`](../how-to/searching.md).

`<DB_USER>`, `<DB_PASSWORD>` and `<DB_NAME>` are the values of the
Compose variables in the same file.

`APP_PORT`, `UI_PORT`, `FORWARD_DB_PORT` and `BIND_ADDRESS` are read by `make`
and by Compose, not by the application: they decide where a run is published on
the host. `APP_PORT` is what `make run` serves on and what the container stack
publishes the API at (`UI_PORT` likewise for the interface); `BIND_ADDRESS`
defaults to `127.0.0.1` everywhere, and changing it publishes a service with no
authentication — see [`../how-to/running-the-stack.md`](../how-to/running-the-stack.md).
