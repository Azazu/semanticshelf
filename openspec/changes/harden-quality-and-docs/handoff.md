# Handoff — harden-quality-and-docs

**Updated:** 2026-09-26 · claude
**State:** awaiting-gate-2
**Branch:** change/harden-quality-and-docs

## Done this session

**The artifacts** — `proposal.md` (**Risk-Tier: medium**, raised from the
roadmap's `low`: four fifths of this change is documentation, and two pieces
are not — a dependency audit that can redden a later change, and a layering
rule the repository will be held to; no Gate 1 at this tier), the two spec
deltas (`http-api-conventions`: every operation carries an example that parses
as the answer it illustrates; `deployment`: the locked dependencies are audited
by CI and by a command), `design.md` with six decisions, and `tasks.md` with
five groups.

**The implementation**

- **The layering rule** (`tests/unit/test_layering.py`): six forbidden arrows
  plus a name allowlist for what a router may take out of SQLAlchemy, each with
  its reason, each watched to fail on a planted violation. The table was refined
  by reading the import graph before asserting it — "routers reach no SQL" as
  first written would have failed on code that is right.
- **`uv audit --locked`** in `make` and in CI's existing `python` job, with its
  preview feature named rather than silenced. Clean here (91 packages); exits 1
  and names four advisories against a throwaway project pinned to an old
  `requests`.
- **The examples FR-OPS-4 owed**: nine, all from real responses, each validated
  by the model the service answers with; the test inverted so a new operation
  without an example fails it; three exemptions with their reasons where the
  rule is enforced.
- **Five screenshots** from a real run, including the two pages the capture
  never visited (Find similar, Upload).
- **The README**, `docs/explanation/architecture.md`, and a documentation index
  that now matches what is on disk.

**The screenshots, re-shot** — the corpus behind them was a fair sample of
COCO, which is how a bathroom and a child brushing their teeth reached the
front page. `scripts/screenshot_corpus.py` now copies the slice worth showing
(an animal, a vehicle, a road sign, somebody playing something, and nothing
else in the frame) into `.data/demo-shopfront`; 80 pictures, imported with
`index-folder` and searched for `people playing tennis on a sunny court`. All
five were re-captured and looked at. Two capture defects it exposed: the Tags
field kept its focus ring, which Streamlit draws in the theme's primary colour
— red here, and a still picture reads that as a refusal; and dropping the focus
onto the heading left Streamlit's anchor link hanging beside it. The recipe and
both commands' exact output are in `docs/how-to/demo-ui.md`, whose screenshot
section still described three pages and named Find similar and Upload as
deliberately absent.

**Checks, in CI's own form** — `FORCE_COLOR=1 CI=true make check` (689
unit/api passed), `openspec validate --all --strict` (17/17), `sh -n
scripts/*.sh` clean, `gate_run_test` 77 passed, `workflow_verify_test` 23
passed, `make audit` clean, and earlier in the change `FORCE_COLOR=1 CI=true
make test-integration` (293 passed) and `make image` (both images built) on a
tree whose image context has not changed since.

## Next step

The user pushes `change/harden-quality-and-docs` and watches CI — which now has
the audit step. On green: `/gate-review harden-quality-and-docs 2`.

One thing for the user to check on the pushed page: that GitHub renders the
README's Mermaid diagram. Nothing local can answer that.

## Blockers

None. `scripts/pregate-verify.sh gate2 harden-quality-and-docs` passes.
