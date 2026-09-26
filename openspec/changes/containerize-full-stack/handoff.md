# Handoff — containerize-full-stack

**Updated:** 2026-09-26 · claude
**State:** fixing-g1
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

## Gate 1 · round 1 — three majors, all accepted
1. **A clean checkout has no configuration.** The compose file demands three
   variables with `:?required` and the file that answers them is gitignored, so
   `docker compose up` on a fresh clone stops at interpolation. The one command
   is now `make stack`: it writes that file from the committed template on first
   run, generating the database password rather than defaulting it, and the
   `:?required` markers stay so a hole in a hand-edited file is still loud.
2. **Inside a container, `127.0.0.1:5433` is that container's own loopback.**
   `migrate`, `api` and `worker` are given a `DATABASE_URL` composed in the
   compose file from the same variables and `db:5432`; the verification runs the
   stack with the host's published port set to something else, which would fail
   if the stack were using it.
3. **The interface hands the browser addresses only its own server can
   resolve.** `ui/client.py` takes `API_PUBLIC_URL` for what the browser
   fetches, defaulting to `API_BASE_URL`; the `demo-ui` spec's "configured by
   the address of the service alone" moves with it. This is the application
   change the design said would be surfaced rather than absorbed — and the proof
   is a headless browser asserting a thumbnail's `naturalWidth`, because a page
   full of broken images answers 200 to `curl`.

## Next step
`/gate-review containerize-full-stack 1 confirm 1`.

## Blockers
None. Nothing in `app/` or `ui/` is expected to change; if the stack turns out
to need an application change, that is a finding to surface rather than absorb.
