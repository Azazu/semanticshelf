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
