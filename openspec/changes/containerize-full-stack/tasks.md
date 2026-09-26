# Tasks — containerize-full-stack

## 1. The image

- [x] 1.1 Read uv's own documentation for its Docker images and pin what it
  names: the base tag (uv version **and** Python version, no floating tag) and
  the flags an image build uses. Verify: the tag and the flags used are quoted
  in the commit body with where they were read; `docker pull <tag>` succeeds.
- [x] 1.2 Write `.dockerignore` first, before any build: `.data/` (weights and
  the demo corpus, gigabytes), `.venv`, `.git`, `tests/`, `docs/`, `openspec/`,
  `.pytest_cache`, `__pycache__`. Verify: `docker build` prints a context size
  in megabytes, not gigabytes, and the number is recorded.
- [x] 1.3 Write `Dockerfile` — builder stage (dependencies layer with
  `--no-install-project`, then the project, both `--locked --no-dev
  --no-editable`), runtime stage (the virtual environment and the migrations,
  `PATH` set to it, an unprivileged user, the media root and model cache created
  and owned by that user), and the interface's **own** builder and image,
  installed with `--only-group ui --no-install-project` rather than layered on
  the runtime stage — a group is added to the project's dependencies, so
  "runtime plus the ui group" would ship the model runtime in the image of a
  thing that must never load a model (design decision 1). Verify: both images
  build; in the service's, `import app` and `import torch` work and
  `import pytest` fails; `id -u` is not 0 in either; sizes recorded (1.79 GB and
  762 MB).
- [x] 1.4 The service's image carries no weights and no interface, and the
  interface's image carries neither the service nor the model runtime — the
  isolation the separate build exists for. Verify, recorded from real runs:
  `MODEL_CACHE` is empty in a fresh service container and `import streamlit`
  fails in it; in the interface's image `import streamlit` and `import httpx`
  work while `import torch`, `import app` and `import pytest` each raise
  `ModuleNotFoundError`; `tests/unit/test_image_definition.py` fails if the
  interface's build stops using `--only-group ui`.
- [x] 1.5 `make image` builds both targets by the same command the CI job runs.
  Verify: `make image` from a clean checkout succeeds and its output is
  recorded.

## 2. The stack

- [x] 2.1 Extend `docker-compose.yml` with `migrate` (one-shot `alembic upgrade
  head`, `restart: "no"`), `api` (uvicorn, `/ready` healthcheck, depends on `db`
  healthy and `migrate` completed successfully), `worker` (`semanticshelf
  worker`, depends on `api` healthy) and `ui` (streamlit, depends on `api`
  healthy), keeping `db` as it is (design decisions 3, 4). Verify:
  `docker compose config` renders without a warning and the dependency
  conditions read back as intended.
- [x] 2.2 Volumes: the database's own, a media volume shared by `api` and
  `worker`, a model-cache volume shared by both. Named, not bind mounts, and
  created in the image owned by the unprivileged user (design decision 5).
  Verify: after an upload, `docker compose down` and `up`, the asset, its file
  and its vectors are still there — recorded from a real run.
- [x] 2.3 Settings: `INDEXING_RUNNER=worker` for `api`, `API_BASE_URL=http://api:8000`
  for `ui`, the in-container `MEDIA_ROOT` and `MODEL_CACHE`, and published ports
  through `${BIND_ADDRESS:-127.0.0.1}` with `APP_PORT` / `UI_PORT` (design
  decisions 6, 7). Verify: `docker compose ps` shows the published addresses
  bound to loopback; an upload with the worker stopped stays `pending` and is
  carried out when it starts.
- [x] 2.4 `make stack`, `make stack-down`, `make stack-logs` and `make
  stack-warm` (the one-shot `models warm` into the cache volume). Verify: each
  runs, and `make help` lists them with one-line descriptions.

## 3. The scan

- [x] 3.1 `make sca-image`: a pinned scanner image run against the built image,
  `--severity HIGH,CRITICAL --ignore-unfixed`, non-zero exit on a finding, its
  database cached in a volume (design decision 8). Verify: the command runs
  against the real image and its summary is recorded in the commit body.
- [x] 3.2 The scan reports what it finds rather than always passing. Verify: run
  it against a deliberately old image (a pinned older base or a known-vulnerable
  public image) and record that it exits non-zero — a scanner that has never
  failed is a scanner nobody has tested.

## 4. CI

- [x] 4.1 Add an `image` job to `.github/workflows/ci.yml`: buildx, layer cache,
  both targets, no registry login, no push, no stack run (design decision 9).
  Verify: the workflow parses; the user's push shows the job green. **Its first
  run was red and the build was not the reason** — both images built and the
  Actions cache service then answered `error writing layer blob: not_found`
  while exporting. Every cache export now carries `ignore-error=true`: a cache
  is an optimisation, and an optimisation may not decide whether a build
  passed.
- [x] 4.2 The job fails when the image cannot be built. Verify: demonstrated
  locally by breaking one `COPY` path and running the same build command, with
  the error recorded; the repository is restored afterwards.

## 5. The stack, actually run

- [x] 5.1 Write `scripts/stack_smoke.sh`: bring the stack up, wait for `/ready`,
  upload one picture, poll the asset until both models report `done`, search for
  it, assert it is found, take the stack down **without** removing volumes
  (design decision 10). Verify: `sh -n` clean; it exits non-zero when the search
  finds nothing (demonstrated by pointing it at an empty query).
- [x] 5.2 Run it for real on a warmed cache, with `APP_PORT`, `UI_PORT` **and
  `FORWARD_DB_PORT`** overridden — the first two because 8000 and 8501 are taken
  on this machine, the third because a stack that quietly used the host's
  published database port would pass every check that leaves it at its default
  (Gate 1 confirmation 1, finding 2). Verify: the transcript is kept and the
  wall time recorded; the exit criterion of the requirements — a clean checkout
  serving the UI and indexing an upload — is what the run shows, and the upload
  is carried out by the worker under the overridden port.
- [x] 5.3 The UI is reachable and shows the corpus. Verify: a recorded
  `curl -sI` of the published UI port and one screenshot-free check that the
  Search page answers (the screenshots themselves belong to change 16).

## 6. Evidence that stays

- [x] 6.1 A test asserting the compose file says what the design says it says:
  every service's dependency condition, every published port bound through
  `BIND_ADDRESS`, `INDEXING_RUNNER=worker` on `api`, and no bind mount where a
  named volume is intended. Verify: `tests/unit/test_compose_stack.py` parses
  the file and fails when any of those is changed.
- [x] 6.2 A test that the image's own contract holds: the runtime target
  installs no `dev` or `ui` group. Verify: a test reads the Dockerfile and fails
  if the runtime stage's sync loses `--no-dev` or gains the `ui` group — a
  static check, because building an image in the unit suite would be a minute
  per run.
- [x] 6.3 A demonstrated failing input for every new check, each run by removing
  that check and nothing else:

  | Guard removed | What failed |
  |---|---|
  | the stack stops telling the API to leave indexing to the worker | 1 failed, 23 passed |
  | a port is published without the address setting | 1 failed, 23 passed |
  | the API stops waiting for the migration to have finished | 1 failed, 23 passed |
  | the services address the database through the host's published port | 3 failed, 21 passed |
  | the project is installed from whatever the build cache had | 1 failed, 23 passed |
  | the interface's image is built with the whole environment | 1 failed, 9 passed |
  | the interface's image loses `PYTHONPATH` | 1 failed, 23 passed |
  | the interface's image runs as root | 1 failed, 23 passed |
  | the readiness probe stops being told where the migrations are | 1 failed, 3 passed |
  | the interface hands the browser the address it calls itself | 2 failed, 14 passed |
  | `scripts/stack-env.sh` stops refusing to overwrite | the second run rewrites a file it did not create |

  Verify: every file was restored afterwards. The sixth row was measured twice:
  the first attempt edited the *comment* above the command and nothing failed,
  which is its own small lesson about what a demonstration proves.

## 7. Documentation

- [x] 7.1 Write `docs/how-to/running-the-stack.md`: the one command, what the
  five services are, what each volume holds and the one command that removes
  them, warming the weights, reading `docker compose ps` when something is not
  ready, the published ports and what they do **not** mean (NFR-SEC-7), the
  measured image sizes and build time, and the smoke transcript. Verify:
  re-read whole after the last edit; every command in it was run in the exact
  form printed.
- [x] 7.2 `docs/how-to/local-development.md` points at it, and
  `docs/reference/settings.md` carries the variables the stack reads that the
  table does not have yet. Verify: both re-read whole; `rg` finds no stale claim
  that the only way to run the service is on the host.
- [x] 7.3 Reconcile the claims this change touches: `rg -n "docker|compose|image"`
  across `docs/`, `openspec/`, `AGENTS.md` and `README.md`, and fix every hit
  that the stack makes wrong. Verify: the terms swept and the files touched are
  named in the commit body.

## 8. Gate 1 round 1 — configuration, the database's address, and the browser's

- [x] 8.1 Finding 1: `make stack` writes the local environment file from the
  committed template when it is absent, generating the database password rather
  than defaulting it, and then brings the stack up; the compose file keeps its
  `:?required` markers (design decision 10a). Verified on a real clone
  (`git clone` into a temporary directory, nothing in it but what git tracks):
  the one command brought `db`, `migrate`, `api`, `worker` and `ui` up and
  `GET /ready` answered
  `{"status":"ready","checks":{"database":"ok","migrations":"ok","models":"ok","media":"ok"}}`;
  a second run of the script said "already there — leaving it alone"; and
  `git status` in that clone was empty afterwards, so nothing it generated is
  anything the repository can see.
- [x] 8.2 Finding 1, the other half: a value the stack needs and does not have
  stops it before any service starts, naming the variable. Verified in the same
  clone *before* the configuration was written — which is the state a clean
  checkout is actually in: `docker compose config` stopped with `error while
  interpolating services.api.environment.DATABASE_URL: required variable
  DB_USER is missing a value: required`, and no service was created. That is
  the failure the `:?required` markers exist for, and it is why the one command
  is `make stack` rather than `docker compose up`.
- [x] 8.3 Finding 2: `migrate`, `api` and `worker` are given a `DATABASE_URL`
  built in the compose file from the same three variables and the service name
  `db:5432`, not from the host's published port (design decision 10b). Verify,
  **all three of them, in one run with `FORWARD_DB_PORT` set to something else
  entirely**: the migration completes (`migrate` exited 0), `/ready` reports the
  database and the revision check passing (`api`), and an uploaded picture
  reaches `done` for every enabled model with the API's own runner switched off
  (`worker` — so the job can only have been carried out by the process that had
  to open its own connection). If any of the three were using the host's port,
  that run would fail. Recorded from the real run of task 5.2, which uses the
  same override.
- [x] 8.4 Finding 3: `ui/client.py` takes `API_PUBLIC_URL` for the addresses it
  hands to the browser, defaulting to `API_BASE_URL`; the stack sets the two to
  the service name and the published address (design decision 10c). Verify:
  `tests/ui` covers both — the default (one address, unchanged behaviour) and
  the split (calls go to one, pictures are addressed by the other) — and fails
  if the default is removed.
- [x] 8.5 Finding 3, proven in a browser rather than in a header: the smoke
  script opens the published interface with the headless browser of the
  `screenshots` group, waits for the corpus and asserts a thumbnail's
  `naturalWidth` is non-zero (design decision 10). Verify: it passes against
  the real stack, and fails when `API_PUBLIC_URL` is pointed at the in-network
  name — which is the defect the reviewer found, reproduced on purpose.
- [x] 8.6 The `demo-ui` spec moves with the code: the requirement that said the
  interface is configured by the address of the service *alone* now covers two
  addresses with the second defaulting to the first. Verify: the delta carries
  the full updated requirement with every scenario it had, plus the two new
  ones; `openspec validate --strict` passes.
- [x] 8.7 Reconcile the exit criterion: `docs/explanation/requirements.md` §7
  row 15 says `docker compose up` on a clean checkout, which cannot hold before
  the configuration exists. It names `make stack` (and what that command does)
  instead. Verify: the row is re-read whole; `rg -n "docker compose up"` across
  `docs/` and `openspec/` leaves no claim that it works on a fresh clone with no
  configuration.

## 9. Closing the change

- [x] 9.1 `openspec validate containerize-full-stack --strict` passes and every
  task above is checked with its evidence. Verify: the command's output is
  recorded.
- [x] 9.2 Run locally everything CI runs, in CI's own form:
  `FORCE_COLOR=1 CI=true make check`, `openspec validate --all --strict`,
  `sh -n scripts/*.sh`, every `scripts/*_test.sh`, and
  `FORCE_COLOR=1 CI=true make test-integration` with the database up — plus the
  image build the new job runs. Verify: 663 unit/api passed, 293 integration
  passed, validation 16/16, `sh -n` clean over every shell script,
  `workflow_verify_test` 23 passed, `gate_run_test` 77 passed, `make image`
  built both targets.
- [x] 9.3 Hand over for the push with `handoff.md` at `awaiting-gate-2` and
  `scripts/pregate-verify.sh gate2 containerize-full-stack` passing. Verify: the
  verifier's output is recorded in the handoff; the gate follows the user's push
  and a green CI run on that exact HEAD.

## 10. What the stack found in the service (apply, after Gate 1)

Two of these are application changes, which the proposal said there would be
none of. They are surfaced rather than absorbed, and Gate 1 is asked again.

- [x] 10.1 `/ready` answered 503 in the stack — `"migrations": "database at
  0003_constraint_names, code head none"` — against a database the stack had
  just migrated. `app/services/readiness.py` computed the migrations' directory
  from the package's own location, which is right for a checkout (`app/` beside
  `alembic/`) and wrong for an installed package, where one level up is
  `site-packages` and the `alembic` there is the library. **The path is now a
  setting**, `ALEMBIC_DIR`, whose default is that same computation, so a host
  run is unchanged; the stack sets the path the image puts them at. Verify:
  `tests/api/test_readiness_migrations.py` covers the default, the environment
  override, a probe pointed at revisions that are not there ("code head none"),
  and that the repository's own default finds a head.
- [x] 10.2 The image shipped stale code, silently. The builder's cache mount
  keeps the wheel uv built for this project, the project's version does not
  change when its source does, and a rebuild after an edit reinstalled the
  previous wheel: a setting added minutes earlier was missing from an image
  built after it. `--reinstall-package semanticshelf` on the project sync fixes
  it. Verify: recorded — before, the image's `app/core/settings.py` had 0
  occurrences of the new constant; after, 2.
- [x] 10.3 The interface's pages import each other as `ui.client`, and
  `streamlit run ui/app.py` puts the *script's* directory on the path, not the
  working directory: every page rendered `ModuleNotFoundError: No module named
  'ui'` where the corpus should be. `PYTHONPATH=/app` in the interface's image.
  Verify: the browser check went from "no picture at all" to two thumbnails
  fetched; on the host `uv run` already added the root, which is why nothing had
  ever noticed.
- [x] 10.4 The artifacts carry all three: `design.md` gets them as decisions
  with what they cost, and `proposal.md` stops saying `app/` is unchanged.
  Verify: `openspec validate --strict` passes and the diff of the proposal says
  what moved.
- [x] 10.5 Gate 1 again, because the scope moved (AGENTS.md: a change of scope
  reopens it). Verify: `scripts/gate-run.sh containerize-full-stack 1 full`
  records a round bound to the commit that carries these.

## 11. Gate 2 round 1

- [x] 11.1 Finding 2 (minor): the how-to said the offline switch in the
  environment file stops the containers asking the Hub, and nothing passed it to
  them — Compose reads that file on the host and hands on only what the compose
  file names. `HF_HUB_OFFLINE` is now passed through to `migrate`, `api` and
  `worker`, the how-to says how, and `tests/unit/test_compose_stack.py` asserts
  it for the two that load models. Verified in a container:
  `HF_HUB_OFFLINE in the container: 1` and `huggingface_hub` reading it as
  `True`.
- [ ] 11.2 Finding 1 (major): the template fills the database's own line and
  leaves a literal in the URL beside it, so the documented host setup created a
  database with one value and connected with another. The template carries the
  marker in both places (a user's edit — the policy plugin does not let me touch
  that file), and `scripts/stack-env.sh` now **refuses** a template that fills
  one and not the other, writing nothing. Verify: the refusal and the success
  were both exercised (nothing written on refusal, no partial left, both lines
  carrying the same generated value on success), and the documented host setup
  runs from a clean clone: `sh scripts/stack-env.sh`, `make init`, `make run`,
  `/ready` answering.
