# Handoff — tune-vector-indexes

**Updated:** 2026-09-25 · claude
**State:** proposing
**Branch:** change/tune-vector-indexes

## Done this session
- Branch `change/tune-vector-indexes` created off `main`; change scaffolded
  with `openspec new change` (schema `spec-driven`).
- `openspec/ROADMAP.md` already carries row 14 for this change — left as is.

## Next step
`/opsx:propose tune-vector-indexes` — measure HNSW against IVFFlat per model
(build time, recall@10 against an exact scan, p95, the `ef_search` curve),
extend `docs/how-to/benchmarks.md`, and record the choice in ADR-002.

## Blockers
None.
