# Handoff — add-assets-and-embeddings-schema

**Updated:** 2026-09-20 · claude
**State:** implementing
**Branch:** change/add-assets-and-embeddings-schema

## Done this session
- Planning artifacts written: `proposal.md` (tier medium with its rationale, non-goals, impact), two delta specs (`asset-storage`, `embedding-storage`), `design.md` (11 decisions, the measurement table behind the storage layout, risks), `tasks.md` (20 tasks with verification).
- The storage-layout decision was measured, not assumed: three layouts built on a throwaway pgvector container (PostgreSQL 16.14, pgvector 0.8.5) with their plans and index sizes, plus an end-to-end probe that the untyped `Vector()` column and the cast expression work through SQLAlchemy and asyncpg without a codec hook. ADR-001 will carry the numbers.
- Strict validation and the mechanical floor pass. Tier medium: no Gate 1.

## Next step
- `/opsx:apply add-assets-and-embeddings-schema`. The user is asked once at the end to push the branch and report the run (task 7.3) before Gate 2.

## Blockers
- None.
