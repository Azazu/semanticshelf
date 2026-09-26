# Proposal — containerize-full-stack

**Risk-Tier:** high

The tier the requirements already declare for this change, and for the reason
they name: CI infrastructure. It also earns it twice over on its own — the
change adds a build that pulls the whole dependency tree into an image, a
process that runs as a different user against volumes holding somebody's media,
and a scanner invocation; and it is the first thing that publishes a port from
anything other than a developer's own loopback. Gate 1 on the artifacts, Gate 2
on the diff, and a demonstrated failing input for every new check.

## Why

The service is complete and it cannot be shown to anybody without a Python
toolchain. Today's route is `make init`, `make run`, `make ui` — uv, a virtual
environment, a database container and three terminals. The brief promised the
other route from its first page (§1: "a one-command Compose stack"), §7 row 15
names it, and its exit criterion is exact: **`docker compose up` on a clean
checkout serves the UI and indexes an upload; CI builds the image.**

There is a second reason, and it is why this comes after stage 3 rather than
before it. The stack is where the worker earns its existence: `INDEXING_RUNNER`
(change 13) exists so that a deployment can hand every unit of extraction work
to a process that is not serving requests. Until now that switch has had no
deployment to switch. The Compose stack is the first place the service runs the
way it was designed to run — API, worker, UI and database as four things —
rather than the way a laptop runs it.

## What Changes

- **A multi-stage `Dockerfile` on the uv base image.** A build stage resolves
  the locked environment (`uv sync --frozen --no-dev --no-editable`, so the
  virtual environment is self-contained and the UI group stays out), a runtime
  stage copies that environment and the application, and a small `ui` target
  adds the UI group and `ui/` for the demo interface. No model weights are baked
  in: they are 2.8 GB, they belong to a cache volume, and an image that carried
  them would be rebuilt every time a checkpoint moved.
- **A `.dockerignore`**, because the build context otherwise carries `.data/`
  (weights and the demo corpus), `.venv`, `.git` and the test tree.
- **A Compose stack of five services**, four of which run: `db` (unchanged,
  pgvector), a one-shot `migrate` that brings the schema to head and exits,
  `api`, `worker` and `ui`. Startup order is governed by health rather than by
  sleeping: `api` starts when the database is healthy and the migration has
  completed, and `worker` and `ui` start when `api` reports ready (NFR-REL-4).
  The API's healthcheck is `/ready` (FR-OPS-2).
- **The stack indexes through the worker.** `INDEXING_RUNNER=worker` is set for
  the API in the stack, so an upload queues and the worker extracts —
  the arrangement change 13 built the switch for. The HTTP contract is
  identical either way; what changes is which process spends the CPU.
- **State lives in volumes, not in containers:** the database's data, the media
  root shared by `api` and `worker`, and the model cache shared by both. A
  `down` and an `up` find the corpus and the weights where they were.
- **Nothing is published beyond loopback by default.** The API and the UI bind
  to `127.0.0.1` through the same `BIND_ADDRESS` the database already uses, and
  the how-to states what exposing them further would require (NFR-SEC-7).
- **`make` grows the stack commands** — bringing it up, taking it down, reading
  its logs, warming the model cache into the volume, building the image and
  **`make sca-image`**, which scans the built image with a pinned scanner image
  and fails on HIGH or CRITICAL findings that have a fix (NFR-SEC-6).
- **CI builds the image on every change**, with a cache, and does not push it
  anywhere. Publishing to a registry is not part of this change (see Non-goals).
- **A how-to page for the stack** — what the four services are, what each
  volume holds, how to warm the weights, how to read `docker compose ps` when
  something is not ready, and what the published ports do and do not mean.

## Capabilities

### New Capabilities

- `deployment`: what the delivered system is, as opposed to what the service
  does. One command brings up a working system and its state survives a
  restart; the runtime image carries the service and neither the development
  tooling, the demo interface nor the model weights; startup order is decided by
  health checks rather than by waiting; in that arrangement the worker is the
  runner; nothing is exposed beyond loopback unless a deployment says so; and
  the image is built by CI and scannable by a published command.

### Modified Capabilities

None. No requirement of any existing capability changes: the HTTP contract, the
queue, the searches and the CLI behave exactly as they do today, which is what
makes this change a delivery change rather than a behaviour change.

## Impact

- **New:** `Dockerfile`, `.dockerignore`, `compose.yaml` services beside the
  existing `db` (the file keeps its name), `docs/how-to/running-the-stack.md`,
  a CI job that builds the image, `make` targets for the stack and the scan,
  and a scripted smoke check the how-to's transcript comes from.
- **Changed:** `Makefile` (new targets), `docker-compose.yml` (four services
  join `db`), `.github/workflows/ci.yml` (the image job),
  `docs/reference/settings.md` and the environment template (the variables the
  stack reads: the published ports, `API_BASE_URL`, the in-container media root
  and model cache), `docs/how-to/local-development.md` (a pointer to the stack
  page), `openspec/ROADMAP.md` and `docs/explanation/requirements.md` §7 row 15
  if the scope moves.
- **Unchanged:** every line of `app/` and `ui/`. If the stack turns out to need
  an application change, that is a finding to surface rather than to absorb —
  a container that needs the program changed to run in it usually means the
  program was reading something it should have been given.
- **Dependencies:** none added to `pyproject.toml`. The scanner runs as a
  pinned container image, not as a Python package.
- **Runtime:** two images from one Dockerfile (the service, and the service plus
  the demo UI). Measured sizes go into the how-to, because an image whose size
  nobody states is an image nobody optimises.

## Non-goals

- **Pushing the image to a registry.** The requirement says CI *builds* it, and
  a build needs no credentials, no package permissions and no decision about
  who may pull it. Publishing is a separate change with its own ADR about what
  the tag means and who may push it.
- **Multiple architectures.** `amd64` only. Cross-building `arm64` under QEMU
  doubles the build and buys nothing for a portfolio nobody runs on an M-series
  server.
- **A production deployment shape.** No Kubernetes manifests, no reverse proxy,
  no TLS, no authentication — the last is a stated boundary of the whole
  project (NFR-SEC-7, D12), and this change documents it rather than changing
  it.
- **Baking the model weights into the image.** They go into a cache volume,
  which `models warm` fills; an air-gapped host is documented, not solved here.
- **GPU support.** CPU-only is a project constraint (§10) and a build that
  cannot be configured onto a GPU should not pretend to be.
- **Changing what the service does.** Not one requirement of an existing
  capability moves in this change.
