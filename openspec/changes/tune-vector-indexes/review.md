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

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-25
**Reviewed-Commit:** 6b25ffe7e4be16378909a57365c3c0d9e46df10a
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `design.md` Applicability; `tasks.md:204-220` | High-tier review requires a demonstrated failing input for every new or changed check. The removal table covers eight checks but omits new input guards claimed in the same design and tasks, including protected schema names and the `--queries` bounds. Tests that pass with the checks present are not the required removal demonstrations. Enumerate the remaining checks and record a failing input for each, or explain which are not new or changed. | open |
| 2 | major | `specs/embedding-storage/spec.md:23-25,43-48`; `design.md` decision 3; `tasks.md:113-118` | The normative phrase "at least nineteen of every twenty of the ten nearest vectors" reads as a per-query guarantee, which for ten neighbours requires all ten, while the design and acceptance task compare the mean recall over 50 queries with 0.95. State explicitly whether the threshold applies to the mean or to every query, and align the requirement, scenario, tasks and ADR decision with that rule. | open |
| 3 | major | `design.md` decision 1 and Risks / Trade-offs; `docs/how-to/benchmarks.md` What the index approximates; `docs/adr/ADR-002-vector-index-family-and-parameters.md:69-75` | The design calls measured recall a floor for real embeddings because a clustered real corpus is supposedly easier than the synthetic one, but the ADR correctly says the direction of the difference is not established. The proposed benchmark contains no comparison with real embeddings that could prove a floor. Remove the directional guarantee from the design and reconcile the explanatory claims, or add evidence and a verification task that supports it. | open |
