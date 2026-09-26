# Handoff — containerize-full-stack

**Updated:** 2026-09-26 · claude
**State:** awaiting-gate-1
**Branch:** change/containerize-full-stack

## Done this session
- Branch and scaffold (`chore(containerize-full-stack): start change`).
- All four planning artifacts written; `openspec validate
  containerize-full-stack --strict` passes and `scripts/pregate-verify.sh gate1`
  is green.
  - `proposal.md` — **Risk-Tier: high** (the tier the requirements declare for
    it: CI infrastructure; it also publishes ports and runs a build that pulls
    the whole dependency tree). Multi-stage Dockerfile on the uv base, a Compose
    stack of `db`, a one-shot `migrate`, `api`, `worker` and `ui`, volumes for
    media and the model cache, `INDEXING_RUNNER=worker` in the stack, loopback
    publication, `make sca-image`, and a CI job that builds the image and
    pushes it nowhere.
  - `specs/deployment/spec.md` — a **new capability**: one command brings the
    system up and health decides the order; the image carries the service and
    neither the tooling, the interface nor the weights, resolved from the same
    lock file, running as an unprivileged user; state outlives the containers;
    in the stack the runner is the worker; nothing is published beyond loopback
    by default; CI builds the image and a published command scans it.
  - `design.md` — ten decisions and the high-tier applicability table. The ones
    worth reading first: migrating is a service that runs once rather than
    something the API does; the worker gets no healthcheck rather than a
    pretend one; named volumes (not bind mounts) are what makes a non-root
    container able to write; the scan is a pinned scanner image and is **not**
    in CI, because a new advisory in a base image should not redden an unrelated
    change.
  - `tasks.md` — 8 groups, 25 tasks, each with its verification.

## Next step
Gate 1, which `high` requires before implementation:
`/gate-review containerize-full-stack 1`.

## Blockers
None. Nothing in `app/` or `ui/` is expected to change; if the stack turns out
to need an application change, that is a finding to surface rather than absorb.
