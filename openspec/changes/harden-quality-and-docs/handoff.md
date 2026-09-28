# Handoff — harden-quality-and-docs

**Updated:** 2026-09-28 · claude
**State:** awaiting-gate-2
**Branch:** change/harden-quality-and-docs

## Done this session

**The artifacts** — `proposal.md` (**Risk-Tier: high**, raised twice: the
roadmap said `low`, the proposal argued `medium`, and Gate 2 round 1 answered
that a mandatory audit step added to CI is the verifier/CI infrastructure the
tier table names), the two spec deltas (`http-api-conventions`: every operation
carries an example that parses as the answer it illustrates;
`deployment`: the locked dependencies are audited by CI and by a command),
`design.md` with six decisions and the high-tier applicability table, and
`tasks.md` with seven groups.

**The implementation**

- **The layering rule** (`tests/unit/test_layering.py`): six forbidden arrows,
  a name allowlist for what a router may take out of SQLAlchemy, and a refusal
  of the whole-package import form no allowlist can cover. Each rule watched to
  fail on a planted violation.
- **`uv audit --locked`** in `make` and in CI's existing `python` job, with its
  preview feature named rather than silenced. Any known advisory reddens the
  run — the command has no severity or fix filter, and the policy now says so
  in every document that states it.
- **The examples FR-OPS-4 owed**: nine, all from real responses, validated
  through the model the service answers with — and validated as the **document
  publishes them**, which is what `app/core/openapi.py` now guarantees.
- **Five screenshots** from a chosen slice of the demo corpus
  (`scripts/screenshot_corpus.py`), and the recipe in `docs/how-to/demo-ui.md`.
- **The README**, `docs/explanation/architecture.md`, a documentation index that
  matches what is on disk, and a commands reference that lists every `make`
  target again.

**Gate 2 round 1 — four majors, all accepted** (§6 of `tasks.md`): the tier;
the published jobs example missing `lease_expires_at` and `last_error` because
FastAPI encodes the document with `exclude_none`; the router SQL guard blind to
`import sqlalchemy as sa`; and an audit policy that said three different things
in three documents.

**Gate 1 round 1 — two majors, both accepted** (§7): the proposal claimed no
service Python changed while the published OpenAPI document is rewritten; and
three tasks were checked on evidence that does not exist yet.

**Checks, in CI's own form** — `FORCE_COLOR=1 CI=true make check` (690
unit/api), `FORCE_COLOR=1 CI=true make test-integration` (293), `openspec
validate --all --strict` (17/17), `sh -n scripts/*.sh`, `gate_run_test` (77),
`workflow_verify_test` (23), `make audit` (clean, 91 packages), and the
seventeen planted failures of §6.5.

## Next step

The user pushed `b17653e` and reported CI green on it, so every task in
`tasks.md` is closed with its evidence. The commit that records that touches
`tasks.md` and this file only.

1. The user pushes again, so the green run is on the head the gates read.
2. `scripts/gate-run.sh harden-quality-and-docs 1 confirm 1` — the fourth
   confirmation of Gate 1 round 1, now that nothing waits on evidence.
3. `/gate-review harden-quality-and-docs 2 confirm 1`, then `/git:merge`.

## Blockers

None.
