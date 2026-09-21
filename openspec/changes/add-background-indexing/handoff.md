# Handoff — add-background-indexing

**Updated:** 2026-09-21 · claude
**State:** proposing
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

`/opsx:propose add-background-indexing`.

Tier is high in the roadmap: this is the project's first concurrency — several
runners claiming the same rows — and delivery is at-least-once, so every
execution must be idempotent. Gate 1 reviews the artifacts before any code.

## Blockers

The integration database was removed during cleanup; a throwaway pgvector
container is created again when the first task needs it (the change's own
tests, not the proposal).
