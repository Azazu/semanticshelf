# Handoff — tune-vector-indexes

**Updated:** 2026-09-25 · claude
**State:** awaiting-gate-2
**Branch:** change/tune-vector-indexes

## Done this session
- Planning artifacts (proposal, spec delta on `embedding-storage`, design,
  tasks), tier **medium**.
- `scripts/bench_schema.py`: the guard that keeps a published benchmark out of
  the service's tables, shared by both commands. `filter_benchmark.py` imports
  it; what it measures, prints and accepts is unchanged.
- `scripts/index_benchmark.py`: per model, a seeded clustered corpus, an exact
  ranking to grade against, four indexes built one at a time (shipped HNSW as
  the migration declares it, HNSW m=32/ef_construction=128, IVFFlat at
  lists = rows/1000 and lists = sqrt(rows)), recall@10 with its worst query, p95
  by nearest rank, both knob curves, and what a narrowed page does under each
  family's strictest iterative scan.
- Evidence: 18 unit tests for the arithmetic and the corpus, 11 integration
  tests (store untouched, schema gone, names refused, the ground truth's plan,
  one index at a time, a miss reported as a miss, the bound cleared at 2 000
  vectors, the iterative-scan values read from the database), and a case in
  `test_import_discipline.py` that the service imports no measurement command.
- The published run at 10 000 assets per model, twice; **ADR-002** written from
  it; `docs/how-to/benchmarks.md` now carries both measurements.
- Reconciliation: NFR-PERF-4's "demo corpus", requirements §3.2 and §7 row 14,
  ROADMAP row 14 (tier), AGENTS.md's index-choice line, `searching.md`.

## The result, in one line
Both bounds are met by the shipped configuration — recall@10 1.000 at
`ef_search` 40 for both models, p95 1.6 ms and 1.2 ms — so design decision 9's
first row applies: no migration, no setting changed, nothing in the service
touched. IVFFlat also loses structurally: it has no `strict_order` iterative
scan, which change 12's narrowed search rests on.

## Next step
The user pushes `change/tune-vector-indexes` and watches CI; on green,
`/gate-review tune-vector-indexes 2`.

## Blockers
None. `scripts/pregate-verify.sh gate2 tune-vector-indexes` — all checks passed
(0 warnings). Locally green: `make check` (602), `make test-integration` (287),
`scripts/workflow_verify_test.sh` (23), `scripts/gate_run_test.sh` (77),
`openspec validate --all --strict` (16/16).
