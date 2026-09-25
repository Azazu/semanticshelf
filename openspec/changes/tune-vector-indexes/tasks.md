# Tasks — tune-vector-indexes

## 1. One guard, shared by both measurement commands

- [x] 1.1 Write `scripts/bench_schema.py`: the schema-name pattern (`\Z`, never
  `$`), the protected names, `SchemaInUse`, the `CREATE SCHEMA` that refuses a
  name already taken, the copy of the service's tables
  (`LIKE ... INCLUDING ALL`, autovacuum off), the resolution check that refuses
  to write unless every unqualified name resolves inside the new schema, and the
  cleanup that drops only a schema this run created (design decision 7). Verify:
  `uv run python -c "import sys; sys.path.insert(0, 'scripts'); import
  bench_schema"` imports it, and `uv run ruff check scripts/bench_schema.py`
  passes.
- [x] 1.2 Make `scripts/filter_benchmark.py` import that module instead of
  carrying its own copy, with no change to what it measures, prints or accepts
  on the command line. Verify: `uv run pytest tests/integration/test_filter_benchmark.py`
  passes with its assertions unchanged, and `git diff` shows no edit to its
  measurement, table or argument parsing beyond the names it now imports.
- [x] 1.3 Let a test that loads a script by file path resolve that import: the
  helper in `tests/integration/test_filter_benchmark.py` puts the scripts
  directory on `sys.path` before executing the module. Verify: the same test
  file passes; removing the `sys.path` line makes it fail with `ModuleNotFoundError`.

## 2. The measurement command

- [x] 2.1 Write `scripts/index_benchmark.py` — the corpus: K seeded centroids on
  the unit sphere, each vector a centroid plus Gaussian noise, normalised, for
  every model in `EMBEDDING_MODELS` at its own width, inserted in batches inside
  the schema `bench_schema.py` owns, then `ANALYZE` (design decision 1). Verify:
  a unit test asserts the vectors are unit length, that a query's tenth nearest
  is measurably nearer than its hundredth on the seeded corpus (so the corpus
  has neighbour structure to find), and that the same seed gives the same
  corpus.
- [x] 2.2 The exact ranking: for each query vector, the ten nearest read with
  `enable_indexscan` and `enable_bitmapscan` off, its plan read and the run
  refused if the plan contains any index scan (design decision 2). Verify: an
  integration test asserts the plan of that statement has no index scan, and
  that the function refuses — with a message naming the plan — when index scans
  are left enabled.
- [x] 2.3 The four configurations per model (design decision 5): the shipped
  HNSW as copied with the tables, HNSW at `m = 32, ef_construction = 128`, and
  IVFFlat at two `lists` values, each built with only its own index present on
  the embeddings copy, each timed as it is built and measured for size with
  `pg_relation_size`. Verify: an integration test asserts that exactly one
  vector index exists on the copy while a configuration is measured, and that
  the plan of the measured query names that index.
- [x] 2.4 `lists` and the probe range come from the installed pgvector's own
  documentation for a corpus of this size, not from memory, and are printed with
  the results. Verify: the version is read at run time
  (`SELECT extversion FROM pg_extension WHERE extname = 'vector'`) and printed
  in the header of the output; the commit body records where the guidance was
  read.
- [x] 2.5 Recall@10 as `|index_top10 ∩ exact_top10| / 10` over Q seeded query
  vectors drawn from the corpus's distribution but not members of it, reported
  as the mean and the worst single query, ties counted by asset identifier
  (design decision 3). Verify: unit tests over the pure function — identical
  rankings give 1.0, disjoint give 0.0, a half-overlap gives 0.5, and a ranking
  that agrees on distance but differs in identity counts as a miss.
- [x] 2.6 Latency: Q timings of one page at `limit = 20` with the service's own
  `effort_for`, one warm-up discarded, p95 by nearest rank
  (`ceil(0.95 × Q)`-th smallest), the query vectors prepared before timing
  starts (design decision 4). Verify: a unit test pins the percentile on a known
  sample (including Q not divisible by 20) against the stated definition.
- [x] 2.7 The curves: `hnsw.ef_search` over 20, 40, 80, 120, 200 and
  `ivfflat.probes` over its matching range, each applied with `SET LOCAL` inside
  the measuring transaction, each reporting recall@10 and p95 (design decision
  6). Verify: the sweep reads `current_setting` back after every step and
  refuses to report when the knob did not take — a knob that was sent and
  ignored gives a flat curve that reads like an index with nothing to gain; and
  an integration test sweeps the shipped index at 1 and at 200 and finds the
  recall moves, which a setting that never applied could not do.
- [x] 2.8 What each family does under a narrowing: which values its
  iterative-scan setting accepts on the installed pgvector, and what a narrowed
  page returns under each (design decision 8). Verify: the command prints that
  per family, and an integration test asserts the setting's accepted values are
  read from the database rather than declared in the script.
- [x] 2.9 Output: Markdown tables — one per model for the configurations, one
  per model for the curves, plus a header naming the corpus size, the seed, the
  distribution's constants, the pgvector version and the effort the service
  would use; `--assets`, `--queries`, `--seed`, `--schema` as options with the
  requirement's size as the default. Verify: `uv run python
  scripts/index_benchmark.py --help` prints them and the output of a small run
  (`--assets 500`) pastes into Markdown unedited.

## 3. Evidence that stays in the suite

- [x] 3.1 `tests/integration/test_index_benchmark.py`: the published command run
  against a populated store leaves every asset, embedding and job exactly as
  they were, the schema it built is gone afterwards, a name already taken is
  refused with its contents intact, and a refused name reaches no database at
  all — the battery `test_filter_benchmark.py` already applies, now over the
  shared module. Verify: `uv run pytest tests/integration/test_index_benchmark.py`
  passes with the database up.
- [x] 3.2 A measurement that cannot report a miss is worthless: a test that asks
  the index to look less far than the ranking requires and asserts the reported
  recall falls below 1 (spec scenario "A miss is reported as a miss"). Verify:
  the test fails when the recall function is replaced by one that returns 1.0,
  and that demonstration is recorded in the commit body.
- [x] 3.3 Recall at the default effort clears the bound on a corpus small enough
  for CI, with margin (design decision 10). Verify: the test states its corpus
  size and threshold, and its wall time is recorded in the commit body so a
  later reader can see what it costs.
- [x] 3.4 Nothing in the service imports either script. Verify: the existing
  layering test covers it, or a case is added to `tests/unit/test_import_discipline.py`.

## 4. The run, and the numbers it produces

- [x] 4.1 Run the published command for real at the requirement's size:
  `uv run python scripts/index_benchmark.py --assets 10000 --seed 7`, with the
  database up and nothing else loading the machine. Verify: its full output is
  kept and the wall time recorded; the run is repeated once to see how far the
  figures move between runs, and both are noted.
- [x] 4.2 Read the result against the two bounds: recall@10 ≥ 0.95 at the
  default effort (NFR-PERF-4) and p95 ≤ 100 ms at `limit = 20` (NFR-PERF-1), per
  model, and take the branch design decision 9 names. Verify: the branch taken
  is stated in the handoff and in ADR-002, with the numbers that chose it; if a
  branch other than the first is taken, its own tasks are added here before the
  work starts.

## 5. What the repository keeps

- [x] 5.1 Extend `docs/how-to/benchmarks.md` with the index measurement: how to
  run it, what it builds, why the corpus is synthetic and why the demo corpus
  cannot serve instead, the tables from task 4.1, and the reading — what the
  numbers mean for a deployment. Change 12's section stays as it is. Verify: the
  page is re-read whole after the last edit and every command in it was run in
  the exact form printed.
- [x] 5.2 Write `docs/adr/ADR-002-vector-index-family-and-parameters.md`: the
  context (what ADR-001 left open), the decision per model with its build
  parameters, the measured evidence, the alternatives and why each lost —
  including the structural argument of design decision 8 — what the record does
  not decide, and what would reopen it. Verify: every number in it came from the
  run of task 4.1; `docs/adr/README.md` gains its row; ADR-001's forward
  reference to ADR-002 now resolves.
- [x] 5.3 Not applicable, and the numbers say why: the shipped configuration met
  both bounds, so no default and no build parameter moved (design decision 9,
  first row). recall@10 1.000 at `ef_search` 40 for both models against a bound
  of 0.95, first miss at `ef_search` 20 (0.996); p95 1.6 ms and 1.2 ms against a
  bound of 100 ms. No revision was added, so `docs/reference/settings.md` and
  `0002_asset_schema` are unchanged and `HNSW_EF_SEARCH` stays 40.

## 6. Reconciling the claims this change touches

- [x] 6.1 Correct NFR-PERF-4 in `docs/explanation/requirements.md`: recall is
  measured on the corpus the measurement builds, at the size NFR-PERF-1 already
  names, because the demo corpus is too small to discriminate — with that reason
  in the text. Verify: `rg -n "demo corpus" docs/explanation/requirements.md`
  leaves no sibling claim saying otherwise.
- [x] 6.2 Fix the claim, not the line: `rg -n "ADR-002|recall|IVFFlat|ef_search"`
  across `docs/`, `openspec/`, `README.md` and `AGENTS.md`, and reconcile every
  hit with what this change measured. Verify: the terms swept and the files
  touched are named in the commit body.
- [x] 6.3 Update `openspec/ROADMAP.md`: row 14's tier (`low` → `medium`, with the
  reason the proposal gives) and its scope line if the work differs from what the
  row promised; the stage-3 narrative gains the one sentence that says the stage
  is closed. Verify: the roadmap is re-read whole.

## 7. Closing the change

- [ ] 7.1 `openspec validate tune-vector-indexes --strict` passes and every task
  above is checked with its evidence. Verify: the command's output is recorded.
- [ ] 7.2 Run locally everything CI runs, in CI's own form:
  `FORCE_COLOR=1 CI=true make check`, `openspec validate --all --strict`,
  `sh -n scripts/*.sh`, every `scripts/*_test.sh`, and
  `FORCE_COLOR=1 CI=true make test-integration` with the database up. Verify:
  all green before the branch is offered for a push.
- [ ] 7.3 Handoff to `awaiting-gate-2` after the user's push and a green CI run
  on that exact HEAD; `scripts/pregate-verify.sh gate2 tune-vector-indexes`
  passes. Verify: its output is recorded in the handoff.
