# Review — add-dinov2-image-search

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** 30015272cea7d69e14d858a7d597255673330fba
**Verdict:** changes-requested

### Findings

| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `design.md`, decision 6 and Concurrent writers; `tasks.md` 5.1 | The concurrency guarantee relies on a unique constraint that does not exist. `app/models/indexing_job.py` and migration `0002_asset_schema.py` give jobs a UUID primary key and non-unique indexes, but no uniqueness on asset/model or unfinished work; migration 0003 only renames CHECK constraints. Two concurrent inserts can both observe no unfinished work and insert different UUIDs, so `ON CONFLICT DO NOTHING` prevents neither duplicate. Specify an actual serialization/uniqueness mechanism compatible with the job lifecycle and other writers; reconcile the no-schema-change claim if necessary. Add a real PostgreSQL concurrent-backfill test, with overlapping transactions and a demonstrated failure when the guard is removed; sequential repetition alone does not verify this guarantee. | fixed |
| 2 | major | `design.md`, decision 5; `tasks.md` 3.2; `specs/image-search/spec.md`, same bounds requirement | Fetching `limit + 2` and removing self in the service does not define correct pagination with the existing repository, which applies OFFSET before returning rows. For a strict ranking `[self, A, B, C, D]`, limit 2 gives `[A, B]` at offset 0, then `[B, C]` at offset 2: a duplicate despite no ties. Self also need not sort first among identical vectors. Specify exclusion relative to the candidate window, ordering, OFFSET, threshold and page cut, and test consecutive pages against the self-excluded ranking. The extra candidate must also be included in the effort budget: at the promised depth 999, self plus the page plus the lookahead needs 1001 candidates, beyond the existing ceiling 1000. Resolve that boundary explicitly in design/spec/tasks and test the deepest accepted page and `has_more`; merely checking self absence and page length misses both defects. | fixed |
| 3 | major | `design.md`, decision 6; `specs/indexing-jobs/spec.md`, later work creation; `tasks.md` 5.1–5.2 | The selection includes an asset with no vector and a terminal failed job, since failed work is not unfinished. Running `index missing` creates a fresh pending job with a fresh attempt budget and retries extraction without resetting the failed job. This conflicts with normative FR-IDX-5 and the unchanged indexing-jobs requirement “The state of an asset's work is visible”, which make an explicit reset the only way failed work runs again. It also means repeated `make demo` can keep retrying exhausted work. Decide whether backfill skips/reports terminal failures or deliberately introduces a new retry policy; reconcile all affected requirements and design claims, and add a failed-job/repeated-command scenario and verification task. | fixed |

### Validation

The branch and HEAD match the requested review target, and the working tree
was clean before this record. Read the proposal, design, tasks, all four delta
specs, repository policy and OpenSpec configuration, and checked the relevant
schema, queue and search implementation and existing requirements.
`openspec validate add-dinov2-image-search --strict` passed. This is an artifact
review; implementation tests were not run.

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** fc105b55adca2665afca2285455d152453043ec8
**Verdict:** changes-requested

### Findings

| # | Resolution |
|---|------------|
| 1 | confirmed — Design decision 6 replaces the nonexistent uniqueness guard with a transaction-scoped advisory lock per model, held before selection through commit. The upload/reset interaction is accounted for without changing queue identity or schema. Task 5.2 requires overlapping transactions on real PostgreSQL and a demonstrated duplicate when the lock is removed. |
| 2 | changes-requested — Exclusion before ordering/OFFSET and the 998 bound resolve the original algorithm and effort-budget defects, but the resolution remains incomplete in `specs/image-search/spec.md` and `tasks.md` 3.2–3.3. The new “One page after another” scenario unconditionally promises each neighbour exactly once, while the same spec retains the text-search tie-boundary exception: the bounded unfiltered window can still select different members of a tied group across requests. Qualify the scenario for an unchanged corpus and pages that do not cut tied groups, preserving the inherited exception. Also add an explicit verification task for actual `/similar` results at `limit + offset = 998`, asserting the returned page and `has_more` with and without an eligible lookahead, plus rejection at 999. Task 3.3 currently checks effort arithmetic and bound acceptance/refusal, not the SQL window or the resulting `has_more`; task 3.2 checks page contents without specifying this boundary. An implementation that grants effort 1000 but fetches only 999 candidates could pass those stated checks and incorrectly report no more results. Require that boundary test to fail when the extra candidate is removed. |
| 3 | confirmed — The selection now excludes pending, running and failed work; the proposal, design and indexing-jobs delta preserve explicit reset as the only retry of terminal failure. Tasks 5.1 and 5.3 cover failed assets, repeated selection, skipped counts and the reset hint, including a demonstrated failure if terminal jobs become eligible again. |

### Validation

Reviewed only the diff from `30015272cea7d69e14d858a7d597255673330fba`
to the Reviewed-Commit and collateral requirements and source reachable from
findings 1–3. The branch and HEAD match the requested target; the working tree
was initially clean. `openspec validate add-dinov2-image-search --strict`
passed. This is a Gate 1 artifact confirmation; implementation tests were not
run. Only this review record was appended; no git write commands were run.

## Confirmation 2 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** 4a6a870a023b5638ba842ee213889379b97c4936
**Verdict:** confirmed

### Findings

| # | Resolution |
|---|------------|
| 1 | confirmed — Design decision 6 specifies a transaction-scoped advisory lock per model before selection, held through commit, instead of relying on nonexistent queue uniqueness. It accounts for upload/reset writers without changing the schema. Task 5.2 requires overlapping transactions on real PostgreSQL and a demonstrated duplicate when the lock is removed. |
| 2 | confirmed — Exclusion occurs above the unfiltered candidate window before ordering, OFFSET and page cutting, preserving the inherited threshold semantics. The 998 depth bound budgets both self and lookahead. The image-search delta now qualifies consecutive-page guarantees for an unchanged corpus without tied groups crossing page edges and explicitly preserves the inherited tie exception. Tasks 3.2–3.4 cover consecutive pages, effort bounds, actual deepest-page items and both values of has_more at limit + offset = 998, rejection at 999, and a demonstrated failure when the extra window candidate is removed. This resolves the remaining objections in Confirmation 1. |
| 3 | confirmed — Backfill eligibility excludes pending, running and failed work, preserving explicit reset as the only retry of terminal failures. The proposal, design and indexing-jobs delta agree; tasks 5.1 and 5.3 cover repeated selection, failed assets, skipped counts and the reset hint, with a demonstrated failure if failed work becomes eligible. |

### Validation

Reviewed only the diff from `30015272cea7d69e14d858a7d597255673330fba`
to `4a6a870a023b5638ba842ee213889379b97c4936` and collateral requirements
and source reachable from findings 1–3, including the remaining objections
recorded in Confirmation 1. The branch and HEAD match the requested target;
the working tree was initially clean. All source-round findings are marked
fixed. `openspec validate add-dinov2-image-search --strict` passed.
This is a Gate 1 artifact confirmation; implementation tests were not run.
Only this review record was appended; no git write commands were run.

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** f4aad30acfe9b3821ac8dfd991c00bacec11049f
**Verdict:** changes-requested

### Findings

| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `ui/shell.py:74–75`; `ui/pages/similar.py:134`; `ui/pages/search.py:91` | The new thumbnail action uses only the asset ID as its Streamlit widget key, but both search pages append subsequent results without deduplication. The search contract explicitly permits overlapping pages when a tied group crosses the bounded candidate window; changes to the corpus between requests can also repeat an asset. Consequently a valid second page containing an already displayed ID makes **More** raise `StreamlitDuplicateElementKey` and abort rendering, including on the existing text-search page which now uses these buttons. Reproduced with the real Similar page in `AppTest` and a stub returning asset `11111111` on both pages: the initial render has no exception; clicking More raises "There are multiple elements with the same key='similar-11111111'". Make rendering tolerate repeated IDs (for example, deduplicate accumulated results while preserving the server offset, or give each rendered occurrence a unique widget key). Add regression coverage that clicks More on overlapping pages, verifies there is no exception, and checks the similar action still targets the correct asset; cover both text and picture search consumers of the shared grid. | fixed |

### Validation

The branch and HEAD match the requested target, and the working tree was clean
before this record. Reviewed the diff from `main`, the proposal, design, tasks,
all four delta specs, prior gate records, repository policy and OpenSpec
configuration. Inspected the search SQL and depth accounting, model adapter
and installed DINOv2 implementation, multipart handling and temporary-file
lifecycle, queue serialization and shared drain, UI, documentation and tests.

`openspec validate add-dinov2-image-search --strict` and `git diff --check`
passed. The existing UI suite passed (45 tests), as did the selected domain,
model-settings, search-policy and index-CLI unit tests (59 tests), using the
installed environment with bytecode and pytest cache writes disabled. An
additional in-memory AppTest reproduction demonstrated finding 1 by clicking
More on overlapping pages. The broader `make test` run, with the installed
Python supplied through `RUN`, was interrupted after it stopped making progress
at the first API test; it did not produce a passing result. Integration and
real-weight suites were inspected but not rerun, and remote CI was not queried.
Only `review.md` was modified; no git write commands were run.
