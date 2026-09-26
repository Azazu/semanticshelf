# Handoff — containerize-full-stack

**Updated:** 2026-09-26 · claude
**State:** ready-to-merge
**Branch:** change/containerize-full-stack

## Done this session
- **Gate 1 · round 1 — confirmed** (three majors: the clean checkout had no
  configuration path, the database was addressed by the host's published port,
  and the interface handed the browser an address only its own server can
  resolve).
- **Implementation**: `Dockerfile` (two images, pinned bases), `.dockerignore`
  (allowlist, 350 kB context), the Compose stack (`db`, one-shot `migrate`,
  `api`, `worker`, `ui`), `scripts/stack-env.sh`, `make image|stack|stack-down|
  stack-logs|stack-warm|sca-image`, the CI `image` job, `scripts/stack_smoke.sh`
  and `scripts/stack_browser_check.py`, and two suites that read the delivery
  definition as structure (`test_compose_stack.py`, `test_image_definition.py`).
- **The real run**: 42.6 s for up → ready → an upload answered `pending` →
  the worker extracting → a search that found it → a browser fetching the
  thumbnail → down with three volumes still there. `make sca-image`: zero
  findings, and it fails on an old base (32 HIGH/CRITICAL, exit 1).
- **Three things the containers found** that the host had hidden, all recorded
  in design.md and §10 of tasks.md: the migrations' path (now `ALEMBIC_DIR`,
  defaulting to the old computation), an image that silently shipped stale code
  (`--reinstall-package`), and an interface that could not import its own pages
  (`PYTHONPATH`). Two of those changed the service and the interface, so —
- **Gate 1 · round 2 — confirmed** after the scope moved. Its finding was mine:
  the proposal promised a separate `--only-group ui` image while the design and
  a task still described the old "runtime plus the ui group" shape, and two
  further sentences repeated it.

## The clean checkout, on a real clone
The template now carries the marker (the user's edit; the policy plugin does not
let me touch that file). Verified by cloning the repository into a temporary
directory and running the one command there:

- before anything wrote configuration, `docker compose config` stopped with
  `required variable DB_USER is missing a value: required` and created nothing —
  the state every clean checkout is in, and the reason the command is
  `make stack`;
- `make stack` wrote the local file with a generated password and brought all
  five services up; `/ready` answered ready on all four checks;
- a second run said "already there — leaving it alone", and `git status` in the
  clone was empty: nothing it generated is anything the repository can see.

## Gate 2 · round 1 — confirmed (confirmation 2)
Two findings, both real, and the second confirmation was the one that mattered:

1. **major** — the template filled the database's own line and left a literal
   beside it in the URL, so the documented host setup created a database with
   one value and connected with another. First fixed with a guard, which the
   confirmation rightly refused: the URL also had the default user, database
   and port baked in. It is **composed** now, from what the written file says,
   and a file that does not say which user and database to use is refused.
   Verified with four fixture templates and end to end on a clone with a
   non-default user, database and port.
2. **minor** — the how-to claimed the offline switch in the environment file
   reached the containers; Compose hands on only what it names. It is passed
   through now, asserted by a unit case and checked inside a container.

Verifying the host flow on a clean clone also found two things the development
machine had hidden: `make init` did not wait for the database (a cold container
meets the migration mid-initialisation), and a second checkout adopts the first
one's containers because the project name comes from the environment file. Both
fixed; the second is in the how-to.

## Next step
`/git:merge containerize-full-stack`, then `/opsx:archive containerize-full-stack`.

## Blockers
None. `scripts/pregate-verify.sh gate2 containerize-full-stack` — all checks
passed. Locally green: `make check` (663), `make test-integration`
(293), `openspec validate --all --strict` (16/16), both script suites,
`make image`.
