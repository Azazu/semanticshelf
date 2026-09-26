# Handoff — containerize-full-stack

**Updated:** 2026-09-26 · claude
**State:** implementing
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

## Blocked on one manual edit
`.env.example` must carry `__GENERATED__` as its database password value —
`scripts/stack-env.sh` replaces that marker when it writes the local file, and
refuses with a message when it is absent. The policy plugin does not let me
read or write that file. Until it is done, tasks 8.1 and 8.2 (the clean-clone
run and the missing-value refusal) cannot be verified.

## Next step
The user makes that one-line edit; then the clean-clone verification, the
handoff to `awaiting-gate-2`, the push, and `/gate-review containerize-full-stack 2`.

## Blockers
Only the edit above. Locally green: `make check` (663), `make test-integration`
(293), `openspec validate --all --strict` (16/16), both script suites,
`make image`.
