# Handoff — add-background-indexing

**Updated:** 2026-09-21 · claude
**State:** implementing
**Branch:** change/add-background-indexing

## Done this session

- Branch and scaffold created. The work, from roadmap row 6 and
  `docs/explanation/requirements.md` §2.4 (FR-IDX-1…8): an uploaded asset
  finally gets its vectors. One job per enabled model enqueued in the same
  transaction as the asset, a runner that claims, executes and finishes them
  through functions the stage-3 worker will reuse, `index_status` in the asset
  representation, the jobs and reindex endpoints, leases for a runner that
  died, bounded retries with backoff, and ADR-003 for the queue's design.

## Next step

Gate 1 passed: Confirmation 3 on `aff810b` reads `confirmed`, all six findings
resolved. Implementation may start — `/opsx:apply add-background-indexing` —
beginning with task group 1 (settings, the claim query, its plan).

## Blockers

The integration database was removed during cleanup; the first task that needs
it recreates a throwaway pgvector container and migrates it.
