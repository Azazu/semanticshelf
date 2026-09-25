# Review — tune-vector-indexes

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-25
**Reviewed-Commit:** 2c90c91d6cb67c6a4cca3752e6513b461b8ecf94
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `proposal.md` Risk-Tier; `scripts/bench_schema.py:59-147`; `scripts/index_benchmark.py:900-912` | The change declares `medium`, but the new `--schema` value is validated and then interpolated into `CREATE SCHEMA`, table DDL, and `DROP SCHEMA ... CASCADE`. The correctness of that input check and the ownership check is the boundary preventing deletion of a user's data. AGENTS.md assigns security-sensitive input handling and deletion to `high` and requires Gate 1 plus demonstrated failing inputs for new checks. Raise the tier and complete the required high-tier review and verification before Gate 2 can pass. | fixed |
| 2 | minor | `tests/integration/test_index_benchmark.py:317-328` | The only automated assertion of recall at the shipped effort exercises `clip-vit-l14`. The added requirement and published decision cover every indexed model, including `dinov2-large`; a regression confined to its width or index would leave this assertion green. Run the same bound check for each model in `EMBEDDING_MODELS`. | fixed |
