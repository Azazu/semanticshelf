# Tasks — containerize-full-stack

## 1. The image

- [ ] 1.1 Read uv's own documentation for its Docker images and pin what it
  names: the base tag (uv version **and** Python version, no floating tag) and
  the flags an image build uses. Verify: the tag and the flags used are quoted
  in the commit body with where they were read; `docker pull <tag>` succeeds.
- [ ] 1.2 Write `.dockerignore` first, before any build: `.data/` (weights and
  the demo corpus, gigabytes), `.venv`, `.git`, `tests/`, `docs/`, `openspec/`,
  `.pytest_cache`, `__pycache__`. Verify: `docker build` prints a context size
  in megabytes, not gigabytes, and the number is recorded.
- [ ] 1.3 Write `Dockerfile` — builder stage (dependencies layer with
  `--no-install-project`, then the project, both `--locked --no-dev
  --no-editable`), runtime stage (the virtual environment and the application,
  `PATH` set to it, an unprivileged user, the media root and model cache created
  and owned by that user), and a `ui` target adding the `ui` group and `ui/`
  (design decision 1). Verify: both targets build; `docker run --rm <image>
  python -c "import app"` works and `import pytest` fails; `id -u` inside is not
  0; `docker images` sizes recorded.
- [ ] 1.4 The image carries no weights and no interface. Verify: a test or a
  recorded command shows `MODEL_CACHE` empty in a fresh container, `streamlit`
  absent from the runtime image and present in the `ui` one.
- [ ] 1.5 `make image` builds both targets by the same command the CI job runs.
  Verify: `make image` from a clean checkout succeeds and its output is
  recorded.

## 2. The stack

- [ ] 2.1 Extend `docker-compose.yml` with `migrate` (one-shot `alembic upgrade
  head`, `restart: "no"`), `api` (uvicorn, `/ready` healthcheck, depends on `db`
  healthy and `migrate` completed successfully), `worker` (`semanticshelf
  worker`, depends on `api` healthy) and `ui` (streamlit, depends on `api`
  healthy), keeping `db` as it is (design decisions 3, 4). Verify:
  `docker compose config` renders without a warning and the dependency
  conditions read back as intended.
- [ ] 2.2 Volumes: the database's own, a media volume shared by `api` and
  `worker`, a model-cache volume shared by both. Named, not bind mounts, and
  created in the image owned by the unprivileged user (design decision 5).
  Verify: after an upload, `docker compose down` and `up`, the asset, its file
  and its vectors are still there — recorded from a real run.
- [ ] 2.3 Settings: `INDEXING_RUNNER=worker` for `api`, `API_BASE_URL=http://api:8000`
  for `ui`, the in-container `MEDIA_ROOT` and `MODEL_CACHE`, and published ports
  through `${BIND_ADDRESS:-127.0.0.1}` with `APP_PORT` / `UI_PORT` (design
  decisions 6, 7). Verify: `docker compose ps` shows the published addresses
  bound to loopback; an upload with the worker stopped stays `pending` and is
  carried out when it starts.
- [ ] 2.4 `make stack`, `make stack-down`, `make stack-logs` and `make
  stack-warm` (the one-shot `models warm` into the cache volume). Verify: each
  runs, and `make help` lists them with one-line descriptions.

## 3. The scan

- [ ] 3.1 `make sca-image`: a pinned scanner image run against the built image,
  `--severity HIGH,CRITICAL --ignore-unfixed`, non-zero exit on a finding, its
  database cached in a volume (design decision 8). Verify: the command runs
  against the real image and its summary is recorded in the commit body.
- [ ] 3.2 The scan reports what it finds rather than always passing. Verify: run
  it against a deliberately old image (a pinned older base or a known-vulnerable
  public image) and record that it exits non-zero — a scanner that has never
  failed is a scanner nobody has tested.

## 4. CI

- [ ] 4.1 Add an `image` job to `.github/workflows/ci.yml`: buildx, layer cache,
  both targets, no registry login, no push, no stack run (design decision 9).
  Verify: the job's YAML is valid (`docker compose config`-equivalent check is
  not applicable, so: the workflow parses in the Actions run the user reports),
  and the user's push shows it green.
- [ ] 4.2 The job fails when the image cannot be built. Verify: demonstrated
  locally by breaking one `COPY` path and running the same build command, with
  the error recorded; the repository is restored afterwards.

## 5. The stack, actually run

- [ ] 5.1 Write `scripts/stack_smoke.sh`: bring the stack up, wait for `/ready`,
  upload one picture, poll the asset until both models report `done`, search for
  it, assert it is found, take the stack down **without** removing volumes
  (design decision 10). Verify: `sh -n` clean; it exits non-zero when the search
  finds nothing (demonstrated by pointing it at an empty query).
- [ ] 5.2 Run it for real on a warmed cache, with `APP_PORT`, `UI_PORT` **and
  `FORWARD_DB_PORT`** overridden — the first two because 8000 and 8501 are taken
  on this machine, the third because a stack that quietly used the host's
  published database port would pass every check that leaves it at its default
  (Gate 1 confirmation 1, finding 2). Verify: the transcript is kept and the
  wall time recorded; the exit criterion of the requirements — a clean checkout
  serving the UI and indexing an upload — is what the run shows, and the upload
  is carried out by the worker under the overridden port.
- [ ] 5.3 The UI is reachable and shows the corpus. Verify: a recorded
  `curl -sI` of the published UI port and one screenshot-free check that the
  Search page answers (the screenshots themselves belong to change 16).

## 6. Evidence that stays

- [ ] 6.1 A test asserting the compose file says what the design says it says:
  every service's dependency condition, every published port bound through
  `BIND_ADDRESS`, `INDEXING_RUNNER=worker` on `api`, and no bind mount where a
  named volume is intended. Verify: `tests/unit/test_compose_stack.py` parses
  the file and fails when any of those is changed.
- [ ] 6.2 A test that the image's own contract holds: the runtime target
  installs no `dev` or `ui` group. Verify: a test reads the Dockerfile and fails
  if the runtime stage's sync loses `--no-dev` or gains the `ui` group — a
  static check, because building an image in the unit suite would be a minute
  per run.
- [ ] 6.3 A demonstrated failing input for every new check of section 6 and for
  the guards of §2: remove each one, record what fails, restore. Verify: a table
  in this file with one row per check, each from one run.

## 7. Documentation

- [ ] 7.1 Write `docs/how-to/running-the-stack.md`: the one command, what the
  five services are, what each volume holds and the one command that removes
  them, warming the weights, reading `docker compose ps` when something is not
  ready, the published ports and what they do **not** mean (NFR-SEC-7), the
  measured image sizes and build time, and the smoke transcript. Verify:
  re-read whole after the last edit; every command in it was run in the exact
  form printed.
- [ ] 7.2 `docs/how-to/local-development.md` points at it, and
  `docs/reference/settings.md` carries the variables the stack reads that the
  table does not have yet. Verify: both re-read whole; `rg` finds no stale claim
  that the only way to run the service is on the host.
- [ ] 7.3 Reconcile the claims this change touches: `rg -n "docker|compose|image"`
  across `docs/`, `openspec/`, `AGENTS.md` and `README.md`, and fix every hit
  that the stack makes wrong. Verify: the terms swept and the files touched are
  named in the commit body.

## 8. Gate 1 round 1 — configuration, the database's address, and the browser's

- [ ] 8.1 Finding 1: `make stack` writes the local environment file from the
  committed template when it is absent, generating the database password rather
  than defaulting it, and then brings the stack up; the compose file keeps its
  `:?required` markers (design decision 10a). Verify: in a clone made into a
  temporary directory (`git clone . <tmp>`), with no local configuration of any
  kind, the one command brings the stack to ready — recorded — and a second run
  changes nothing; nothing secret is added to the repository (`git status` in
  that clone is clean afterwards).
- [ ] 8.2 Finding 1, the other half: a configuration that exists but is missing
  a value stops the stack before any service starts, naming the variable.
  Verify: remove one line from the generated file, run the command, record the
  message; restore.
- [ ] 8.3 Finding 2: `migrate`, `api` and `worker` are given a `DATABASE_URL`
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
- [ ] 8.4 Finding 3: `ui/client.py` takes `API_PUBLIC_URL` for the addresses it
  hands to the browser, defaulting to `API_BASE_URL`; the stack sets the two to
  the service name and the published address (design decision 10c). Verify:
  `tests/ui` covers both — the default (one address, unchanged behaviour) and
  the split (calls go to one, pictures are addressed by the other) — and fails
  if the default is removed.
- [ ] 8.5 Finding 3, proven in a browser rather than in a header: the smoke
  script opens the published interface with the headless browser of the
  `screenshots` group, waits for the corpus and asserts a thumbnail's
  `naturalWidth` is non-zero (design decision 10). Verify: it passes against
  the real stack, and fails when `API_PUBLIC_URL` is pointed at the in-network
  name — which is the defect the reviewer found, reproduced on purpose.
- [ ] 8.6 The `demo-ui` spec moves with the code: the requirement that said the
  interface is configured by the address of the service *alone* now covers two
  addresses with the second defaulting to the first. Verify: the delta carries
  the full updated requirement with every scenario it had, plus the two new
  ones; `openspec validate --strict` passes.
- [ ] 8.7 Reconcile the exit criterion: `docs/explanation/requirements.md` §7
  row 15 says `docker compose up` on a clean checkout, which cannot hold before
  the configuration exists. It names `make stack` (and what that command does)
  instead. Verify: the row is re-read whole; `rg -n "docker compose up"` across
  `docs/` and `openspec/` leaves no claim that it works on a fresh clone with no
  configuration.

## 9. Closing the change

- [ ] 9.1 `openspec validate containerize-full-stack --strict` passes and every
  task above is checked with its evidence. Verify: the command's output is
  recorded.
- [ ] 9.2 Run locally everything CI runs, in CI's own form:
  `FORCE_COLOR=1 CI=true make check`, `openspec validate --all --strict`,
  `sh -n scripts/*.sh`, every `scripts/*_test.sh`, and
  `FORCE_COLOR=1 CI=true make test-integration` with the database up — plus the
  image build the new job runs. Verify: all green before the branch is offered
  for a push.
- [ ] 9.3 Hand over for the push with `handoff.md` at `awaiting-gate-2` and
  `scripts/pregate-verify.sh gate2 containerize-full-stack` passing. Verify: the
  verifier's output is recorded in the handoff; the gate follows the user's push
  and a green CI run on that exact HEAD.
