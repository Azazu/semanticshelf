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
| 1 | major | `design.md` Applicability; `tasks.md:204-220` | High-tier review requires a demonstrated failing input for every new or changed check. The removal table covers eight checks but omits new input guards claimed in the same design and tasks, including protected schema names and the `--queries` bounds. Tests that pass with the checks present are not the required removal demonstrations. Enumerate the remaining checks and record a failing input for each, or explain which are not new or changed. | fixed |
| 2 | major | `specs/embedding-storage/spec.md:23-25,43-48`; `design.md` decision 3; `tasks.md:113-118` | The normative phrase "at least nineteen of every twenty of the ten nearest vectors" reads as a per-query guarantee, which for ten neighbours requires all ten, while the design and acceptance task compare the mean recall over 50 queries with 0.95. State explicitly whether the threshold applies to the mean or to every query, and align the requirement, scenario, tasks and ADR decision with that rule. | fixed |
| 3 | major | `design.md` decision 1 and Risks / Trade-offs; `docs/how-to/benchmarks.md` What the index approximates; `docs/adr/ADR-002-vector-index-family-and-parameters.md:69-75` | The design calls measured recall a floor for real embeddings because a clustered real corpus is supposedly easier than the synthetic one, but the ADR correctly says the direction of the difference is not established. The proposed benchmark contains no comparison with real embeddings that could prove a floor. Remove the directional guarantee from the design and reconcile the explanatory claims, or add evidence and a verification task that supports it. | fixed |

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** 6874f5654dec6b31d29e6876482bfecf60f18a08
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — `tasks.md` §8.6 now records removal demonstrations for the protected schema names, `--queries` bounds, shipped-index refusal, and empty-input guards; the affected query and shipped-index tests were updated. |
| 2 | confirmed — the requirement, scenario, design, ADR and benchmark guide explicitly bind 0.95 to mean recall over at least fifty queries and publish the lowest single-query recall separately; the integration check now uses fifty queries. |
| 3 | changes-requested — `design.md` decision 1 still says that an index is easy where data is clustered and, more directly, that real vectors would show a real distribution is *easier* than the synthetic corpus (`design.md:78-99`). The benchmark guide repeats the former claim (`docs/how-to/benchmarks.md:213-214`). These claims conflict with the revised risks section and ADR-002, which say the direction is not established. Remove or qualify the remaining directional claims. |
