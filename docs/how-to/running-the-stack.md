# Run the whole thing in containers

Four processes and a database, from a checkout, with nothing on the host but
Docker: no Python, no uv, no virtual environment.

```console
$ make stack
```

That is the one command. On a clean checkout it first writes the local
environment file from the committed template, replacing the marker in it with a
value generated on the spot (`scripts/stack-env.sh`), and then brings the stack
up and waits until it is healthy. It prints where to go:

```text
api:  http://127.0.0.1:8000/api/docs
ui:   http://127.0.0.1:8501
```

Ports come from the environment, because those two are often taken:

```console
$ APP_PORT=8010 UI_PORT=8511 FORWARD_DB_PORT=5444 make stack
```

## What is running

| Service | What it is | Waits for |
|---|---|---|
| `db` | PostgreSQL 16 with pgvector | — |
| `migrate` | `alembic upgrade head`, once, then exits | `db` healthy |
| `api` | the service, uvicorn on 8000 | `db` healthy **and** `migrate` exited successfully |
| `worker` | `semanticshelf worker`: claims queued work and extracts vectors | `api` healthy |
| `ui` | the Streamlit demo on 8501 | `api` healthy |

Nothing sleeps waiting for anything. `db` is healthy when `pg_isready` says so,
`api` when `/ready` answers 200 — which is the probe that covers the database,
the migration head, the media root and the model declarations in one answer.

**The worker has no healthcheck**, deliberately: a command that grepped a
process list would report a runner stuck on a lease as healthy. Where a stuck
worker actually shows is the queue — `GET /api/v1/jobs` and
`GET /api/v1/stats`.

**In the stack the API extracts nothing.** It runs with
`INDEXING_RUNNER=worker`, so an upload is stored, queued and answered, and the
worker does the model work in its own process. Stop the worker and uploads keep
succeeding with their vectors `pending`.

## The weights, and the first search

The images carry no model weights: they are 2.8 GB, and they live in a volume
instead. The first search or index in a fresh stack downloads them, which is
slow once and never again. To do it deliberately, before anybody watches:

```console
$ make stack-warm
```

That runs `semanticshelf models warm` through the service image into the same
volume. Once the cache is warm, `HF_HUB_OFFLINE=1` in the environment file stops
the containers from asking the Hub anything at all (they still check a few
metadata endpoints otherwise, which is what the worker's log shows on a first
run).

## What survives

| Volume | Holds |
|---|---|
| `<project>_pg_data` | the database |
| `<project>_media` | uploaded pictures and their thumbnails, shared by `api` and `worker` |
| `<project>_models` | the model cache |

```console
$ make stack-down      # stops the stack; all three volumes stay
$ docker compose down -v   # removes them — the corpus, the vectors and the weights
```

`make stack-down` is a stop. The `-v` form is the only thing here that deletes
anything, and it deletes all of it.

## Ports, and what they do not mean

Every published port binds to `${BIND_ADDRESS}`, which defaults to `127.0.0.1`:
the stack is reachable from the machine that runs it and from nowhere else.
Changing that address publishes a service with **no authentication** — that is a
stated boundary of this project, not an oversight (NFR-SEC-7). Anything beyond a
trusted network needs a reverse proxy that authenticates in front of it.

Inside the stack the services find each other by name, so the published ports
are for the person at the keyboard: the interface calls the API at
`http://api:8000`, and the pictures it shows are addressed at the **published**
API address, because a browser on the host cannot resolve `api`. That is what
`API_PUBLIC_URL` is for, and the stack sets it from `APP_PORT`.

## Is it really working?

```console
$ sh scripts/stack_smoke.sh
```

It brings the stack up, waits for `/ready`, uploads a picture, checks that the
API answered `pending` for both models rather than extracting anything itself,
waits for the worker to finish, searches for the picture, and then opens the
interface in a real browser to see that the thumbnail *rendered* — a page of
broken images answers 200 to `curl`, so the last step asks the browser for
`naturalWidth` instead. Then it takes the stack down and checks the volumes are
still there.

It runs with `FORWARD_DB_PORT` overridden on purpose: if any service reached the
database through the port the host publishes rather than through `db:5432`, this
is where that would show.

One run on this machine, with the model cache already warm:

```text
== bringing the stack up (project semanticshelf-stack, api 8010, ui 8511, db 5444)
 ✔ Container semanticshelf-stack-db-1       Healthy
 ✔ Container semanticshelf-stack-migrate-1  Exited
 ✔ Container semanticshelf-stack-api-1      Healthy
 ✔ Container semanticshelf-stack-worker-1   Started
 ✔ Container semanticshelf-stack-ui-1       Started

== the API says
{"status":"ready","checks":{"database":"ok","migrations":"ok","models":"ok","media":"ok"}}

== uploading /tmp/stack-smoke-XXXX.png
asset 7784b9b5-c229-415f-be84-7039d3a38a91
queued, not extracted by the API: {"clip-vit-l14": "pending", "dinov2-large": "pending"}

== waiting for the worker (up to 900s)
indexed after 10s: {"clip-vit-l14": "done", "dinov2-large": "done"}

== searching for it
found it, score 0.169

== opening the interface in a browser
browser-check:   256px  http://127.0.0.1:8010/api/v1/assets/7784b9b5-.../thumbnail
browser-check: 2 picture(s) fetched by the browser itself

== taking the stack down (volumes are kept)
volumes still there: 3

== stack-smoke: the stack served the interface and indexed an upload
```

Forty-three seconds, warm.

## The images

```console
$ make image
```

Two images from one `Dockerfile`, both on pinned bases (`python:3.12-slim-trixie`
with uv 0.12.19 copied in from its own published image):

| Image | Size | What it carries |
|---|---|---|
| `semanticshelf:runtime` | 1.79 GB | the service, its locked dependencies, the migrations. Most of it is `torch` |
| `semanticshelf:ui` | 762 MB | Streamlit, httpx and `ui/` — **no model runtime and no `app`** |

The interface's image is built with `--only-group ui`, so "the interface never
loads a model" is true of the image and not only of the code: `import torch`
inside it fails.

Neither image runs as root, neither contains the test or lint tooling, and the
build context is 350 kB because `.dockerignore` is an allowlist — without it,
`.data/` alone (weights and the demo corpus) would send gigabytes to the daemon.

## The scan

```console
$ make sca-image
```

A pinned Trivy image against the built service image: HIGH and CRITICAL
findings that have a fix, non-zero exit if there are any, its vulnerability
database cached in a volume. On the image as published here it reports zero, in
the OS packages and in every Python package. It fails when there is something to
fail on: the same command against `python:3.9-slim-bullseye` reports 32
HIGH/CRITICAL in the OS and 4 in the Python packages and exits 1.

It is not part of CI. A new advisory in a base image would otherwise redden an
unrelated change; NFR-SEC-6 asks for the scan before a release tag, and this is
the command that does it.

## When something is not ready

```console
$ docker compose ps
$ make stack-logs
$ curl -s http://127.0.0.1:8000/ready | python3 -m json.tool
```

`/ready` names the check that failed. Two that are worth recognising:

- `"migrations": "database at <revision>, code head none"` — the probe cannot
  find the migration scripts. In the stack they are at `/app/alembic` and
  `ALEMBIC_DIR` says so; on a host they are found beside the package.
- `"media": ...` — the media root is missing or not writable. In the stack it is
  a named volume created from the image, owned by the unprivileged user the
  process runs as. A **bind** mount would arrive with the host's ownership
  instead, which that user cannot write to; that is why the stack uses named
  volumes.

## Running it beside a development database

`make stack` and `make up` are the same Compose project, so `db` is the same
container and the same volume: the stack and a host `make run` share one
database, which is convenient until it is not. To keep them apart, give the
stack its own project and its own published port:

```console
$ COMPOSE_PROJECT_NAME=semanticshelf-stack FORWARD_DB_PORT=5444 \
      APP_PORT=8010 UI_PORT=8511 make stack
```

Its volumes are then named after that project, and nothing it does touches the
development corpus.
