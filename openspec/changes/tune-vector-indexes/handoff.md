# Handoff — tune-vector-indexes

**Updated:** 2026-09-26 · claude
**State:** ready-to-merge
**Branch:** change/tune-vector-indexes

## Done this session
- **Gate 2 · round 1 — confirmed** (confirmation 1, commit `4ccede8`). Both
  findings closed: the tier is `high` with everything that asks for — the
  applicability table, thirteen checks each with a demonstrated removal, and the
  guard's own unit and integration suites — and the shipped-effort recall test
  covers every model in `EMBEDDING_MODELS`, as the mean over fifty queries.
- **Gate 1 · round 1 — confirmed** (confirmation 2) after three majors: the
  incomplete enumeration of checks, the per-query reading of the 0.95 bound, and
  the directional claim about real embeddings.
- The change itself: `scripts/bench_schema.py` (one guard, both benchmarks),
  `scripts/index_benchmark.py`, 30 unit and 12 integration tests of its own,
  ADR-002, and `docs/how-to/benchmarks.md` with both measurements.

## The result
Nothing in the service changed, and that is the finding: at 10 000 vectors per
model the shipped HNSW (`m = 16`, `ef_construction = 64`, `ef_search` 40)
returns the whole ranking — mean recall@10 1.000, worst query 1.00, p95 1.6 ms
and 1.2 ms against a bound of 100 — and IVFFlat has no `strict_order` iterative
scan for a narrowed search to rest on.

## Next step
`/git:merge tune-vector-indexes`, then `/opsx:archive tune-vector-indexes`.

## Blockers
None. Locally green: `make check` (635), `make test-integration` (293),
`openspec validate tune-vector-indexes --strict`, `scripts/pregate-verify.sh
gate2 tune-vector-indexes`; CI green on the reviewed HEAD.
