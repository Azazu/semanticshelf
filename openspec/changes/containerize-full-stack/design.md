# Design — containerize-full-stack

## Context

See `proposal.md` — Why. What shapes the approach is what is already true:

- `pyproject.toml` locks everything with uv, and the PyTorch **CPU** index is
  declared `explicit = true` with `torch` pinned to it, so any `uv sync` — on
  the host, in CI or in an image — installs CPU wheels without being told.
- Dependency groups already separate what the service needs from what the
  development and the demo interface need (`dev`, `ui`, `screenshots`).
- `docker-compose.yml` exists and holds one service, `db` (pgvector 16), with a
  healthcheck, a named volume and a loopback-bound published port from
  `BIND_ADDRESS` / `FORWARD_DB_PORT`.
- The application already has everything a container needs from it: settings
  from the environment only, `/health` and `/ready` (FR-OPS-1/2), a CLI with
  `worker`, `models warm` and the import commands, `INDEXING_RUNNER` deciding
  which process carries out queued work, and a UI that speaks only HTTP and
  reads `API_BASE_URL`.
- CI runs `make check` and the integration suite against a pgvector service;
  `uv.lock` is checked by `make lock-check`.
- On this machine ports 8000 and 8501 are taken by another project, so every
  local run of the stack uses `APP_PORT` / `UI_PORT` overrides — which is also
  the case the published-port settings exist for.

## Goals / Non-Goals

**Goals**

- One command from a clean checkout to a working system, with nothing on the
  host but Docker.
- An image that is honest about what it contains: the service, its locked
  dependencies, no development tooling, no interface, no weights.
- Evidence that the stack does what the exit criterion says — an upload
  indexed by the worker and found by a search — recorded from a real run.
- A scan and a CI build, neither of which publishes anything anywhere.

**Non-Goals** (beyond the proposal's)

- No orchestration beyond Compose, no service discovery, no secrets manager:
  the stack reads the same environment file the host run already uses.
- No attempt to make the image small for its own sake. It carries `torch`; the
  size is what it is, it is measured, and the how-to states it.

## Applicability (high tier)

| Question | Answer |
|---|---|
| **Deletion / expiry** | Nothing in this change deletes data. The stack's state is in named volumes, which `docker compose down` leaves alone; only `down -v` removes them, and the how-to says so in the one place a reader would run it. The smoke script takes the stack down without `-v`, and it names the volumes it expects to still be there afterwards. |
| **Security-sensitive input handling** | No new request path and no new parsing. What is new is *exposure*: ports. Every published port binds through `BIND_ADDRESS` (default `127.0.0.1`), the same setting the database already uses, and the how-to states what exposing them further would require (NFR-SEC-7). The scanner and the image build take no input from a request. |
| **External side effects** | Three: the image build pulls from package indexes, the first search or index in a fresh stack pulls model weights from the Hugging Face Hub (NFR-SEC-4, already documented), and the scan pulls a pinned scanner image. All three are operator actions, none is reachable from a request, and `HF_HUB_OFFLINE=1` plus a warmed cache volume make the second one optional. Nothing is pushed anywhere. |
| **Crash before / after an external effect** | A container that dies mid-work leaves the queue as change 13 designed it: the lease expires and another runner takes the unit. A migration that fails leaves the stack without an API, by construction — `api` waits for the migration to complete successfully, so a half-migrated schema cannot be served. |
| **Concurrent writers** | The API and the worker share one media root; they already do on a host, and the write order (file first, row second, thumbnail beside it) is change 5's. Two workers in the stack would be two runners on one queue, which change 13 measured. The one new race is the *first* start: `migrate` runs alone and `api` waits for it, so no two processes migrate at once. |
| **Authorization boundary** | n/a — no authentication exists by design (D12, NFR-SEC-7), and the stack does not invent one. What it does is refuse to publish beyond loopback by default, and say so. |
| **Idempotency of retries** | `docker compose up` twice is once: the migration is idempotent (Alembic at head is a no-op), volumes are reused, and the services are recreated only when their definition changed. The smoke script is safe to re-run; it names its own asset and cleans up after itself. |
| **Money rounding** | n/a. |
| **Empty / zero / null inputs** | The stack's inputs are settings. Every one it reads has a default except the three the database is named and opened by, which the compose file marks `:?required` so a missing value fails at parse time with the variable's name rather than at runtime with a connection error. A clean checkout has none of them — the file that holds them is gitignored — so the command writes that file from the committed template first, generating the one value that must not be committed (decision 10a). |

Every check named above has a test or a demonstrated failure; §6 of `tasks.md`
records each one.

## Decisions

### 1. One Dockerfile, two targets, the environment built once

Stages: a **builder** on uv's own Python 3.12 image that installs the locked
environment in two layers — dependencies first (`--no-install-project`), then
the project — and a **runtime** stage that copies `/app/.venv` and the
application, sets `PATH` to the virtual environment and runs as an unprivileged
user. A third target, **ui**, is the runtime stage plus the `ui` dependency
group and `ui/`.

The flags are uv's own recommendations for an image, and each earns its place:
`--locked` (the build fails if `uv.lock` is stale, which is the image's half of
`make lock-check`), `--no-dev` and no `ui` group (what the image must not
carry), `--no-editable` (the virtual environment holds the code, so the runtime
stage needs no source tree), `UV_COMPILE_BYTECODE=1` (startup, paid once at
build) and `UV_LINK_MODE=copy` (cache mounts and the final copy live on
different filesystems).

*Alternative considered:* two Dockerfiles, one per image. Rejected — the two
differ by one dependency group and one directory, and two files that must stay
in step is the defect this project has already paid for twice (a copied
benchmark harness in change 13, a copied guard in change 14).

*The base image tag is read from uv's documentation at implementation time and
pinned* — both the uv version and the Python version — rather than tracked by a
floating tag.

### 2. Weights are not in the image; the cache is a volume

CLIP and DINOv2 are 2.8 GB. In the image they would be pulled on every rebuild,
they would make the build depend on the Hub being up, and they would be wrong
the moment a checkpoint setting changed. So `MODEL_CACHE` points at a volume,
the first use fills it, and `models warm` (FR-CLI-5, which exists for exactly
this) fills it deliberately through a one-shot run of the same image. The
how-to shows both, and states what `HF_HUB_OFFLINE=1` buys once the cache is
warm.

### 3. Migrating is a service that runs once, not something the API does

`migrate` runs `alembic upgrade head` and exits; `api` depends on it having
completed successfully, and on `db` being healthy. The alternative — migrating
in the API's entrypoint — is the common shortcut and it is wrong here for two
reasons: two API containers would race the same migration, and a service that
migrates whatever database it is pointed at is a service that can rewrite a
schema nobody asked it to. `/ready` already refuses to report ready when the
schema is not at head (FR-OPS-2), so the failure mode is visible either way;
this decision only decides who is allowed to fix it.

### 4. Order comes from health, never from sleeping

`db` keeps its `pg_isready` healthcheck. `api` gets one on `/ready`, which is
what FR-OPS-2 says Docker healthchecks use — it covers the database, the
migration head, the media root and the model declarations in one answer. The
worker and the UI wait on `api` being healthy (NFR-REL-4).

The worker has no HTTP surface and gets **no** healthcheck rather than a
pretend one: a command that greps a process list would report "healthy" for a
worker stuck on a lease. What it gets instead is a restart policy and the
queue's own visibility (`/jobs`, `/api/v1/stats`), which is where a stuck
runner is actually seen.

### 5. Not the superuser, and the volumes are writable anyway

The image creates the media root and the model cache at fixed paths owned by an
unprivileged user, and runs as that user. Docker initialises a **named** volume
from the image's content at that path, ownership included, so the first `up`
finds both writable. A **bind** mount does not work that way: it arrives with
the host's ownership, and a non-root container cannot write to it. That is a
real trap, so the stack uses named volumes, the how-to states the bind-mount
case, and the failing case is demonstrated once rather than discovered by
somebody else.

### 6. In the stack, the runner is the worker — through the switch that exists

`INDEXING_RUNNER=worker` is set for the `api` service, and nothing else changes.
No new environment variable, no compose-only mechanism: change 13 built the
switch for this arrangement, and this is the arrangement.

### 7. What is published, and where it binds

`api` publishes `${BIND_ADDRESS:-127.0.0.1}:${APP_PORT:-8000}` and `ui`
publishes `${BIND_ADDRESS:-127.0.0.1}:${UI_PORT:-8501}`, matching how `db`
already publishes. Inside the network the UI reaches the API by service name
(`API_BASE_URL=http://api:8000`), so the published ports are for the person at
the keyboard, not for the stack's own wiring — which is what makes binding them
to loopback free.

### 8. The scan is a pinned scanner image, not a dependency

`make sca-image` runs a pinned Trivy image against the locally built image,
with `--severity HIGH,CRITICAL`, `--ignore-unfixed` and a non-zero exit on a
finding, and its database cache in a volume so a second run is quick. It is a
container rather than a Python package because the scanner has nothing to do
with the service's dependency tree and must not enter its lock file.

*The scan is not in CI in this change.* Scanning on every push turns a new
advisory in a base image into a red build on an unrelated change; NFR-SEC-6
asks for the scan "before a release tag", and there are no tags yet. CI builds;
the operator scans. Said plainly in the how-to so the command is not forgotten.

### 9. CI builds the image, and that is all it does with it

A job that builds both targets with buildx and a layer cache, without logging
into any registry and without loading the image into the runner's daemon. It
does not run the stack: that needs the real weights (2.8 GB) and the model
downloads NFR-SEC-4 documents, which is not what a pull request should pay for.

### 10a. A clean checkout has no configuration, so the command writes it

The compose file demands `DB_NAME`, `DB_USER` and `DB_PASSWORD` with
`:?required`, and the file that answers them is gitignored — only its template
is committed. So `docker compose up` in a fresh clone fails during
interpolation, before a service starts (Gate 1 round 1, finding 1).

`make stack` is therefore the one command: when the local environment file is
absent it writes one from the committed template, replacing the database
password placeholder with a value generated on the spot
(`tr -dc` over `/dev/urandom`, so the host needs nothing but a shell), and then
brings the stack up. On every later run it finds the file and changes nothing.

*The `:?required` markers stay.* They are what makes a missing value a failure
that names the variable instead of a default nobody chose, and a generated file
does not make them redundant — someone who edits it by hand can still leave a
hole.

*Alternative considered:* defaults in the compose file
(`${DB_PASSWORD:-semanticshelf}`). Rejected: a password in a committed file is a
password in the repository, whatever its value is, and the first deployment to
publish beyond loopback inherits it.

*Alternative considered:* `POSTGRES_HOST_AUTH_METHOD=trust`, which removes the
password question entirely. Rejected for the stack that is meant to look like a
deployment: trust authentication on a service other containers can reach is not
what this project wants to show, even bound to loopback. It stays what it is
today — the integration database's own arrangement, on a throwaway container.

### 10b. Inside the stack the database is `db:5432`

The committed template points `DATABASE_URL` at the host's published port
(`127.0.0.1:5433`), which is correct for `make run` on the host and wrong inside
every container, where that address is the container's own loopback (Gate 1
round 1, finding 2). `migrate`, `api` and `worker` are therefore given a
`DATABASE_URL` composed in the compose file from the same three variables and
the service name, which also means the host's `FORWARD_DB_PORT` can move
without touching the stack.

### 10c. The interface needs two addresses, and that is an application change

`ui/client.py` builds absolute URLs from the API's links and hands them to the
browser (`address_of` → `st.image`). With `API_BASE_URL=http://api:8000` the
browser is given `http://api:8000/...`, which only the interface's own server
can resolve: every thumbnail in the stack would be a broken image, and a
`curl -sI` of the UI's port would not notice (Gate 1 round 1, finding 3).

So the interface takes two settings: `API_BASE_URL`, the address it calls, and
`API_PUBLIC_URL`, the address pictures are given to the browser under —
defaulting to `API_BASE_URL`, so a host run is configured exactly as it is
today. In the stack they are `http://api:8000` and
`http://127.0.0.1:${APP_PORT}`.

This is a change to `ui/`, which the proposal said would not change. That is the
right outcome of the rule rather than an exception to it: the design said a
stack that needs an application change is a finding to surface, the reviewer
found it, and the scope moved through the gate rather than around it. The
`demo-ui` spec's "configured by the address of the service alone" moves with it.

*Alternative considered:* the interface fetches the bytes itself and renders
them from memory. Rejected — it doubles the traffic through a demo process, it
makes a picture's size a Streamlit memory question, and FR-UI-2's shape (every
picture comes from a URL the API gave) is what keeps the interface honest.

*Alternative considered:* `extra_hosts: host.docker.internal:host-gateway` and
one address for both. Rejected: platform-dependent, and it points the
interface's server at the host's published port to reach a service one network
hop away.

### 10. The end-to-end evidence is a scripted local run

`scripts/stack_smoke.sh` brings the stack up, waits for `/ready`, uploads one
picture, polls the asset until its vectors are `done`, searches for it, asserts
it is found, and takes the stack down without touching the volumes. It is the
exit criterion, executable. The how-to's transcript is its output; the tasks
require it to have been run for real, with the model cache warmed first so the
run does not measure the Hub.

**It also opens the interface in a browser.** A page that renders every
thumbnail as a broken image answers 200 to `curl`, so the last step drives the
headless browser this repository already has (the `screenshots` group's
Playwright, used by `scripts/screenshots.py`): open the published UI, wait for
the corpus, and assert that a thumbnail's `naturalWidth` is not zero — which is
the browser saying it fetched the bytes, and the only check that could have
caught decision 10c's defect.

## Risks / Trade-offs

- **The image is large** (`torch` alone is hundreds of megabytes) → measured and
  stated rather than hidden; the CPU index keeps it from being far worse, and
  the UI image is a thin layer on top of the runtime one rather than a second
  full environment.
- **A build that pulls from the network can fail for reasons the change did not
  cause** → the lock file pins every Python dependency, the base image is
  pinned, and the scanner image is pinned. What remains unpinned is the registry
  being up, which no design fixes.
- **Named volumes hide state from a newcomer** ("why is my corpus still there?")
  → the how-to lists every volume, what it holds, and the one command that
  removes them.
- **A non-root container plus a bind mount is a permission error nobody expects**
  → demonstrated once, documented, and avoided by using named volumes.
- **The stack could turn out to need an application change** (a setting that is
  read from a file rather than the environment, a path the service assumes) →
  that is a finding to surface, not to absorb quietly: the proposal says the
  application is unchanged, and if it cannot be, the scope goes back through
  Gate 1.
- **Compose version drift**: `docker compose` (v2, the plugin) is assumed; the
  how-to states the version the run was made with, and the smoke script checks
  for the plugin rather than failing obscurely halfway.

## Migration Plan

Nothing to migrate: the stack is additive, and the host workflow
(`make init` / `make run` / `make ui`) keeps working exactly as it does. A
deployment that was never containerised has nothing to roll back; a person who
does not want the stack simply does not start it.

## Open Questions

None that change the specs, the approach or the tasks. Publishing the image to a
registry is deliberately out of scope (proposal, Non-goals) rather than
undecided.
