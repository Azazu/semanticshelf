# Handoff — harden-quality-and-docs

**Updated:** 2026-09-28 · claude
**State:** ready-to-merge
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

Every task in `tasks.md` is closed with its evidence. The user pushed
`b17653e` and then `60dbb53` and reported both CI runs green (2026-09-28);
`b17653e` is the last commit that changed anything but the protocol files
`review.md`, `handoff.md` and `tasks.md`, which are the three
`scripts/workflow-verify.sh merge` allows to differ from a reviewed commit and
the only three a gate's own record-keeping touches.

**Gate 1** — waived by the user at `cfb8cae` after six confirmations: finding 1
was confirmed throughout, and what remained of finding 2 was a condition no
record can satisfy, since the evidence that CI is green on a commit can only be
written in a later one. **Gate 2** — confirmed at `53f841a`, all four findings.

Then CI went red on the pushed branch, in a test this change never touched:
three integration helpers ordered rows by `created_at`, which is the same
instant for everything written in one transaction, so two of them asserted an
order the heap decided (§8 of `tasks.md`). All three order by something total
now. That is code outside the protocol files, so the Gate 2 decision it was
confirmed under is stale.

Gate 2 was confirmed again on that fix (`5973886`).

Next: `/git:merge harden-quality-and-docs`, then `/opsx:archive`.

## Blockers

None.
