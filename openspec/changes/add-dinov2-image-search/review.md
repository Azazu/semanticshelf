# Review — add-dinov2-image-search

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** 30015272cea7d69e14d858a7d597255673330fba
**Verdict:** changes-requested

### Findings

| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `design.md`, decision 6 and Concurrent writers; `tasks.md` 5.1 | The concurrency guarantee relies on a unique constraint that does not exist. `app/models/indexing_job.py` and migration `0002_asset_schema.py` give jobs a UUID primary key and non-unique indexes, but no uniqueness on asset/model or unfinished work; migration 0003 only renames CHECK constraints. Two concurrent inserts can both observe no unfinished work and insert different UUIDs, so `ON CONFLICT DO NOTHING` prevents neither duplicate. Specify an actual serialization/uniqueness mechanism compatible with the job lifecycle and other writers; reconcile the no-schema-change claim if necessary. Add a real PostgreSQL concurrent-backfill test, with overlapping transactions and a demonstrated failure when the guard is removed; sequential repetition alone does not verify this guarantee. | open |
| 2 | major | `design.md`, decision 5; `tasks.md` 3.2; `specs/image-search/spec.md`, same bounds requirement | Fetching `limit + 2` and removing self in the service does not define correct pagination with the existing repository, which applies OFFSET before returning rows. For a strict ranking `[self, A, B, C, D]`, limit 2 gives `[A, B]` at offset 0, then `[B, C]` at offset 2: a duplicate despite no ties. Self also need not sort first among identical vectors. Specify exclusion relative to the candidate window, ordering, OFFSET, threshold and page cut, and test consecutive pages against the self-excluded ranking. The extra candidate must also be included in the effort budget: at the promised depth 999, self plus the page plus the lookahead needs 1001 candidates, beyond the existing ceiling 1000. Resolve that boundary explicitly in design/spec/tasks and test the deepest accepted page and `has_more`; merely checking self absence and page length misses both defects. | open |
| 3 | major | `design.md`, decision 6; `specs/indexing-jobs/spec.md`, later work creation; `tasks.md` 5.1–5.2 | The selection includes an asset with no vector and a terminal failed job, since failed work is not unfinished. Running `index missing` creates a fresh pending job with a fresh attempt budget and retries extraction without resetting the failed job. This conflicts with normative FR-IDX-5 and the unchanged indexing-jobs requirement “The state of an asset's work is visible”, which make an explicit reset the only way failed work runs again. It also means repeated `make demo` can keep retrying exhausted work. Decide whether backfill skips/reports terminal failures or deliberately introduces a new retry policy; reconcile all affected requirements and design claims, and add a failed-job/repeated-command scenario and verification task. | open |

### Validation

The branch and HEAD match the requested review target, and the working tree
was clean before this record. Read the proposal, design, tasks, all four delta
specs, repository policy and OpenSpec configuration, and checked the relevant
schema, queue and search implementation and existing requirements.
`openspec validate add-dinov2-image-search --strict` passed. This is an artifact
review; implementation tests were not run.
