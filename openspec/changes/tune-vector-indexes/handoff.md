# Handoff — tune-vector-indexes

**Updated:** 2026-09-25 · claude
**State:** implementing
**Branch:** change/tune-vector-indexes

## Done this session
- Branch and scaffold (`chore(tune-vector-indexes): start change`).
- All four planning artifacts written and `openspec validate
  tune-vector-indexes --strict` passes:
  - `proposal.md` — **Risk-Tier: medium**, raised from the roadmap's `low`
    because the change moves the guard that keeps a published measurement
    command out of the service's tables and adds a second command beside it.
    Gate 2 only; no Gate 1 (no new architecture).
  - `specs/embedding-storage/spec.md` — one added requirement: what the vector
    index approximates is measured, published and bounded (recall@10 ≥ 0.95 at
    the default effort on ≥ 10 000 vectors per model, an exact ground truth, a
    reproducible command that cannot touch the store, the decision recorded as
    an ADR).
  - `design.md` — ten decisions: a seeded clustered synthetic corpus and why the
    demo corpus cannot serve, an exact ground truth proven by its plan, the
    recall and p95 definitions, four index configurations measured one at a
    time, the two knob curves, the shared guard, IVFFlat's narrowed behaviour as
    structural evidence, where a shortfall lands, and what CI keeps.
  - `tasks.md` — 7 groups, 24 tasks, each with its verification.

## Next step
`/opsx:apply tune-vector-indexes` — implement in task order: the shared
`scripts/bench_schema.py` first (with `filter_benchmark.py` unchanged in
behaviour), then `scripts/index_benchmark.py`, then the evidence, the real run
at 10 000 vectors per model, ADR-002 and the documents.

## Blockers
None. The database container is currently down (`make up` before the
integration work).
