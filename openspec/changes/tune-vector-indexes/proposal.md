# Proposal — tune-vector-indexes

**Risk-Tier:** medium

The roadmap carried this change as `low`, and for its visible half that is
right: a measurement command, a table in a how-to, an ADR. The half that raises
it is the guard between a published command and the person's own corpus. That
guard exists because an earlier version of `scripts/filter_benchmark.py` erased
this repository's demo corpus while change 12 was being measured; this change
moves it into a module a second command shares and adds that second command
beside it, which creates and drops schemas of its own. Gate 2 reads that diff.
Gate 1 is not needed: no new architecture, and the artifacts here are a
measurement plan.

## Why

ADR-001 chose the storage layout — one `embeddings` table, one partial HNSW
index per model over the dimension cast — and said outright what it did not
choose: whether HNSW is the right family at all, whether `m = 16` and
`ef_construction = 64` are the right build parameters, and what recall the
defaults actually give. It named ADR-002 as the record that would answer this,
and ADR-002 does not exist.

The brief has carried the shape of that answer since it was written:
**NFR-PERF-1** (p95 ≤ 100 ms for `limit = 20` over 10 000 embeddings per model,
the query embedding excluded), **NFR-PERF-4** (recall@10 ≥ 0.95 against an exact
scan at the default effort, with the `ef_search` 20 → 200 trade-off curve
recorded), and §3.2 of the requirements, which sends the whole HNSW-versus-
IVFFlat question — build time, recall, latency, filtered-query behaviour — to
this change, per model.

Until it is measured, every search this service answers is approximate by an
unknown amount. Change 12 measured *which plan* answers a narrowed query. This
change measures *what the index gives up* when it is the plan that answers, and
either confirms the shipped configuration against the two bounds the brief
states or shows which of them it misses.

## What Changes

- **A published measurement command, `scripts/index_benchmark.py`.** For each
  model the store indexes, in a schema of its own: build the corpus, build each
  candidate index, and report what each one costs and what it gives up — build
  time, index size, recall@10 against an exact scan of the same corpus, the
  latency distribution of one page at the service's own effort, and the curves
  (`hnsw.ef_search` across the documented 20 → 200 range, `ivfflat.probes` over
  its matching range). The ground truth is an exact scan, never another
  approximate index, and its plan is read to prove it.
- **The shipped index is measured as the migration builds it.** The benchmark
  copies the service's tables (`LIKE ... INCLUDING ALL`) as change 12's already
  does, so the HNSW index under measurement is the one a request meets, at the
  parameters `0002_asset_schema` states. Only the alternatives are declared by
  the script.
- **The guard is shared, not copied.** Schema ownership, the resolution check
  before the first write, the refusal of a name already taken and the cleanup
  that drops only what was created move into one module both commands import.
  Copying a harness instead of sharing it was change 13's Gate 2 finding 2: a
  broken original cannot be caught by tests that exercise a copy.
  `filter_benchmark.py`'s behaviour and its published numbers do not change.
- **`docs/how-to/benchmarks.md` grows its second measurement**, the way the
  roadmap says it should: change 12's narrowed-plan section stays, and the index
  section joins it — tables from a real run, with the corpus, the machine and
  the reading.
- **ADR-002** records the decision per model with that evidence: which family
  the store uses, at which build parameters, what recall and latency they give
  at the shipped effort, what the alternatives cost, what the record does not
  decide, and what would reopen it. `docs/adr/README.md` gains its row.
- **What the measurement finds is applied, within this change's reach.** If the
  shipped configuration satisfies NFR-PERF-1 and NFR-PERF-4, nothing in the
  service changes and the ADR records why — that is the expected outcome and it
  is still a result. If recall at the default effort falls short, the default
  `HNSW_EF_SEARCH` moves and `docs/reference/settings.md` moves with it. If the
  build parameters are wrong, a migration rebuilds the index — the requirements'
  own acceptance criterion for this change ("the chosen parameters applied by
  migration if they changed"). A finding that the *family* is wrong is a
  structural change: this change stops there, the ADR records the finding, and
  the rebuild is proposed on its own, because swapping the index family also
  reopens the narrowed-search contract change 12 wrote against HNSW's
  `strict_order` iterative scan.
- **Two claims in the brief are reconciled with what can be measured.**
  NFR-PERF-4 asks for recall@10 "on the demo corpus": that corpus is at most 500
  pictures (`demo-dataset download --count`, default 500) and 20 on this
  machine, a size at which the index returns everything and recall is 1 by
  construction — it cannot carry the measurement. The requirement is corrected
  to name the corpus the measurement uses, at the size NFR-PERF-1 already fixes.
  §7's row for this change is reconciled with the tier and the scope above.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `embedding-storage`: one added requirement. The store's lookup is already
  required to be answered from an index; nothing yet says what that index
  approximates. The added requirement makes the approximation a measured,
  published and bounded property — recall@10 at the shipped effort, the curve
  around it, an exact scan as the ground truth, and a command that reproduces
  all of it without being able to touch the store. It derives NFR-PERF-4 and the
  measurement half of NFR-PERF-1 into the capability that owns the index.

## Impact

- **New:** `scripts/index_benchmark.py`, the shared schema module both benchmark
  commands import, `docs/adr/ADR-002-*.md`, unit tests for the measurement's
  arithmetic, integration tests for the command's promises.
- **Changed:** `scripts/filter_benchmark.py` (imports the shared module; no
  behaviour change), `tests/integration/test_filter_benchmark.py` (loads the
  script with its directory importable), `docs/how-to/benchmarks.md`,
  `docs/adr/README.md`, `docs/explanation/requirements.md` (NFR-PERF-4 and the
  §7 row), `openspec/ROADMAP.md` (tier), and — only if the numbers say so —
  `app/core/settings.py` with `docs/reference/settings.md`, or a new Alembic
  revision rebuilding an index.
- **Unchanged:** the HTTP contract, the search service, the repositories, the
  ORM metadata, the queue. No API code is touched by the measurement.
- **Dependencies:** none added. The corpus is built with the standard library's
  `random` and the vectors are written as text, as change 12's benchmark already
  does; nothing here needs numpy, a model or a network.
- **Runtime:** the command is an operator command. Nothing in the service, the
  worker or the UI imports it, and a test proves the layering.

## Non-goals

- **Changing the index family.** IVFFlat is measured here, not adopted here. If
  it wins, that is a finding and a new change, because the narrowed-search
  contract of change 12 is written against HNSW's `strict_order` iterative scan
  and would have to be reopened with it.
- **Tuning anything but the vector index.** The tag and metadata GIN indexes,
  the claim index and the listing index are out of scope; change 12 measured the
  plans they take part in.
- **A performance gate in CI.** Timings on a shared runner measure the runner.
  What CI keeps is the deterministic part: that the measurement's ground truth
  is exact, that its recall figure can report a miss, and that the command
  cannot touch the store.
- **Real model vectors.** The corpus is synthetic and seeded, and the design
  says why: what is compared is two index families over one distribution, and a
  real model's vectors would add a variable nobody can hold still. The demo
  corpus's size is reported as the reason it cannot serve instead.
- **Rewriting change 12's section of `benchmarks.md`.** It measured a different
  question and its numbers stand.
