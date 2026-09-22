# Review — add-text-to-image-search

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-22
**Reviewed-Commit:** e61bb8eab2e2c31308871ce70adbb1a20c45dda1
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `app/repositories/embeddings.py:124`; `openspec/changes/add-text-to-image-search/design.md:84` | Pagination is applied in the inner query before the UUID tie-break: `ORDER BY distance LIMIT/OFFSET` chooses an arbitrary subset of an equal-distance group, and the outer `ORDER BY distance, asset_id` can only sort that already-chosen subset. When a tie straddles a page boundary, repeated requests or adjacent pages can therefore swap, duplicate, or omit tied assets instead of using the identifier as the global tie-break required by `specs/text-search/spec.md`. Design decision 7 explicitly accepts this case, so it is a known contract violation rather than merely a missing test; the existing tie tests keep both tied rows on one page and cannot expose it. | fixed |
