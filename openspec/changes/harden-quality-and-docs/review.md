# Review — harden-quality-and-docs

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** b9fe520c2ffda98bdb038c7156770136a9968299
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `proposal.md:3-12`; `.github/workflows/ci.yml:105-112`; `AGENTS.md` Risk tiers | This change adds a mandatory dependency-audit step to CI. `AGENTS.md` explicitly assigns verifier/CI infrastructure to `high`, but the proposal declares `medium` and skipped Gate 1. Raise the tier and reconcile the required Gate 1 review before treating this change as merge-ready. | fixed |
| 2 | major | `app/schemas/jobs.py:76-116`; `tests/api/test_openapi_examples.py:70-87,142-154` | The published `GET /api/v1/assets/{asset_id}/jobs` example drops `lease_expires_at` and `last_error` from each job because FastAPI encodes `responses=` with `exclude_none`. Both fields are required, though nullable, in `IndexingJobRead`. Validating the example extracted from `create_app().openapi()` with `IndexingJobList.model_validate` produces four missing-field errors. The test validates the original constant and deliberately strips its nulls for document comparison, so it misses the invalid example and the delta spec's requirement that the published example parse as the answer. | fixed |
| 3 | major | `tests/unit/test_layering.py:114-121,166-181` | The router SQL guard examines only `ast.ImportFrom`. A router can add `import sqlalchemy as sa` and call `sa.select(...)` without the guard seeing it; the general forbidden-edge table also has no router-to-`sqlalchemy` rule. Thus the new test does not enforce NFR-QA-2's "routers contain no SQL" promise. Cover direct package imports and demonstrate the check failing on that form. | fixed |
| 4 | major | `Makefile:82-86`; `docs/explanation/requirements.md:278`; `openspec/changes/harden-quality-and-docs/specs/deployment/spec.md` | The normative NFR-SEC-6 requires CI to fail on known HIGH/CRITICAL advisories with a fix. `make audit` runs plain `uv audit --locked`, which has no severity or fix-availability filter here, while the delta spec silently broadens the failure condition to any fixable vulnerability. Reconcile the normative requirement, delta spec, and implemented failure policy; demonstrate the chosen policy on a failing input. | fixed |

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** c16f82c13123a6631ed7c76e1543e34ca70aec8e
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `proposal.md:98-110`; `design.md:45-48,181-183`; `app/core/openapi.py` | The proposal says service behaviour is unchanged and that the only Python changes are schema examples and tests. The change also modifies OpenAPI generation in `app/core/openapi.py` and its installation in `app/main.py` to restore nullable fields in the served document. This is a change to the service's published output and a new implementation mechanism for the delta spec's example guarantee. State that scope and mechanism accurately in the proposal and design so Gate 1 reviews the change actually being made. | fixed |
| 2 | major | `tasks.md:31-35,88-95,139-142`; `handoff.md:59-65`; branch status | Tasks 1.3, 3.2 and 5.3 are checked even though their verification requires a pushed branch, green CI and the user's report that GitHub rendered the Mermaid diagram. The handoff still asks the user to push and check the diagram, and this branch is ahead of its remote. Record only completed evidence as done; leave the pending external verification open until it occurs. Checked tasks must have evidence, and each task must be feasible at its lifecycle point. | fixed |
