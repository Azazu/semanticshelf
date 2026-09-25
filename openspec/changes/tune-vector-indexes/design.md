# Design — tune-vector-indexes

## Context

See `proposal.md` — Why. What shapes the approach is what already exists:

- One `embeddings` table holds every model; each model key has one **partial
  HNSW cosine index over the dimension cast**, built by `0002_asset_schema` with
  `m = 16, ef_construction = 64` (ADR-001). Every vector query carries the cast
  or the index is not used.
- `scripts/filter_benchmark.py` already measures a narrowed search, and it
  already owns the pattern this change needs: a corpus built in a schema the
  script creates, tables copied from the service's own with
  `LIKE ... INCLUDING ALL`, a resolution check before the first write, and a
  cleanup that drops only a schema the run created. That pattern exists because
  an earlier version of it truncated the service's tables and erased this
  repository's demo corpus.
- The search service decides how hard the index looks:
  `effort_for(settings, limit, offset)` → `max(HNSW_EF_SEARCH, limit+offset+1)`,
  capped at pgvector's 1000, applied with `SET LOCAL` inside the search's
  transaction. The default `HNSW_EF_SEARCH` is 40.
- The brief fixes the two bounds this change reports against: **NFR-PERF-1**
  (p95 ≤ 100 ms at `limit = 20` over 10 000 embeddings per model, query
  embedding excluded) and **NFR-PERF-4** (recall@10 ≥ 0.95 at the default
  effort; the `ef_search` 20 → 200 curve recorded).
- CI runs the integration suite against `pgvector/pgvector:pg16`, so whatever
  evidence this change leaves behind as a test runs there on every push.

## Goals / Non-Goals

**Goals**

- One command that produces every number ADR-002 needs, per model, reproducibly
  from a seed, and that a reader can re-run.
- A ground truth that is exact by construction and shown to be exact by its
  plan.
- The same store-safety promise change 12 made, made once and shared, so that
  neither command can drift from it.
- Evidence in CI for the parts that are deterministic; the timings stay in the
  document where they belong.

**Non-Goals** (beyond the proposal's)

- No abstraction over index families beyond what the measurement needs: the
  script builds DDL strings for two families and reads two GUCs. A plug-in
  architecture for a third would be invented for nobody.
- No change to how the service chooses its plan at runtime. The narrowed-query
  behaviour of IVFFlat is *measured* here to inform the decision; the service's
  own narrowed search keeps the contract change 12 wrote.
- No sampling framework. Q query vectors, one seed, the arithmetic written out.

## Decisions

### 1. The corpus is synthetic, clustered and seeded — not uniform, not the demo corpus

A uniform sample on the unit sphere in 768 dimensions has no neighbour
structure: every pair is nearly orthogonal, the ten nearest are separated from
the ten-thousandth by almost nothing, and recall@10 measured over it reports how
the index broke a near-tie rather than whether it found the neighbours. Real
embeddings are the opposite — clustered, anisotropic, with genuine near
neighbours — and an index is easy exactly where the data is clustered.

So the corpus is built as **K seeded centroids drawn on the sphere, each vector
a centroid plus Gaussian noise, normalised**; K and the noise scale are
constants of the script, printed with the results, and chosen so that a query's
ten nearest are meaningfully nearer than its hundredth. Vectors are unit length,
which is what the service stores (cosine on L2-normalised rows).

*The demo corpus cannot serve instead.* `demo-dataset download` takes at most a
few hundred pictures (default 500) and holds 20 on this machine. At that size an
HNSW scan with `ef_search = 40` visits a sizeable fraction of the graph and
returns the exact ten every time: recall is 1 by construction and discriminates
nothing. That is a fact worth publishing rather than hiding — the how-to states
it, and NFR-PERF-4's "on the demo corpus" is corrected to the corpus the
measurement uses, at the size NFR-PERF-1 already fixes (10 000 per model).

*Alternative considered:* real CLIP and DINOv2 vectors over a larger fetched
corpus. Rejected for this change: it needs weights, a network fetch and hours of
CPU, and it would make the comparison depend on a distribution nobody can hold
still between runs. What it would add — that a real distribution is *easier*
than this one — is stated as the direction of the bias instead.

### 2. The ground truth is an exact scan, proven by its plan

For each query the exact ten nearest are read with index scans disabled for that
transaction (`enable_indexscan`, `enable_bitmapscan` off), which leaves a
sequential scan of the model's rows and a sort. The script **reads the plan of
that statement** and refuses to continue unless it contains no index scan: a
ground truth produced by the index it grades would report 1.00 for everything
and look like success.

*Alternative:* computing distances in Python from the same rows. Rejected — it
would measure a different distance implementation, not the store's.

### 3. Recall@10 is a set intersection, reported as a mean and a worst case

For each of Q seeded query vectors (default 50, drawn from the corpus's
distribution but not members of it), recall is
`|index_top10 ∩ exact_top10| / 10`. The command reports the mean over Q and the
worst single query, because a mean of 0.97 hiding one query at 0.4 is the shape
that matters to somebody's search. Ties at equal distance are counted by asset
identifier, so a tie broken differently by the two rankings is a miss — the
conservative direction.

### 4. Latency is p95 by nearest rank, warm, and excludes the query embedding

Q timings of one page (`limit = 20`, the service's own `effort_for`), one warm-up
run discarded, taken around the execution of the statement the repository
builds, client-side, as `filter_benchmark.py` already times. p95 is the
nearest-rank percentile of the Q samples (`ceil(0.95 × Q)`-th smallest), stated
in the document so nobody has to guess which of the several definitions it is.
The query vector is prepared before timing starts: NFR-PERF-1 excludes the
embedding, and this measurement has no model in it at all.

### 5. What is measured: four configurations per model, one at a time

| Configuration | Where it comes from |
|---|---|
| HNSW as shipped (`m = 16`, `ef_construction = 64`) | copied with the tables, built by the migration's own DDL |
| HNSW wider (`m = 32`, `ef_construction = 128`) | declared by the script |
| IVFFlat at pgvector's guidance for this size | declared by the script |
| IVFFlat at a second `lists` value | declared by the script |

The shipped configuration is never re-declared: the tables are copied
`LIKE ... INCLUDING ALL`, so the HNSW index under measurement is the index a
request meets and cannot drift from the migration. Each configuration is
measured with **only its own index present** on the embeddings copy — the others
dropped — so the planner has no choice to make and the plan is read to confirm
which index answered. `lists` and the probe range are taken from pgvector's own
documentation for a corpus of this size, and the implementation task verifies
them against the installed version rather than against memory.

### 6. The knob curves are the same measurement at several settings

`hnsw.ef_search` over 20, 40, 80, 120, 200 — the range NFR-PERF-4 names, with
the service's default among them — and `ivfflat.probes` over its matching range,
each reporting recall@10 and p95. Every setting is applied with `SET LOCAL`
inside the measuring transaction, the way the service applies its own.

### 7. The store-safety guard is shared, not copied

Everything that stands between a published command and somebody's corpus moves
into one module under `scripts/` that both commands import: the name pattern
(with `\Z`, never `$` — change 12, Gate 2 finding 1), the protected names, the
`CREATE SCHEMA` that refuses a name already taken, the copy of the service's
tables, the resolution check that refuses to write unless every unqualified name
resolves inside the new schema, and the cleanup that drops only a schema the run
created.

Copying it instead would repeat change 13's Gate 2 finding 2 exactly: a harness
that duplicates what it should be exercising cannot fail when the original
breaks. Sharing it means the existing integration tests of
`filter_benchmark.py` — the ones that run the published command against a
populated store — now also cover the module the new command depends on.

*Import mechanics.* `scripts/` is not a package and is not installed;
`python scripts/x.py` puts `scripts/` first on `sys.path`, so a plain module
import resolves. The tests that load a script by file path
(`spec_from_file_location`) do not get that for free, so they put the directory
on `sys.path` before loading. No packaging change, no `__init__.py`, nothing
added to the wheel — `app/` stays the only packaged code, and a unit test
already proves nothing in the service imports a script.

### 8. IVFFlat's behaviour under a narrowing is part of the evidence

Change 12's narrowed-search contract rests on `hnsw.iterative_scan =
strict_order`: the scan keeps going until the page is filled or a stated bound
stops it, and the answer reports `scan_limited` when it was the bound. Whether
IVFFlat can give the same thing, or only a relaxed order, decides more than
latency — it decides whether adopting it would reopen that contract. The command
therefore records, per family, what the iterative-scan setting accepts and what a
narrowed page returns under it. The answer goes into ADR-002 as a structural
argument beside the numbers, and the implementation task establishes it from the
installed pgvector rather than from documentation read once.

### 9. Where a shortfall lands

| What the numbers say | What this change does |
|---|---|
| Both bounds met by the shipped configuration | Nothing in the service changes; ADR-002 records the evidence and the margin |
| Recall short at the default effort, met at a higher one | `HNSW_EF_SEARCH` default moves; `docs/reference/settings.md` moves with it |
| Build parameters clearly better at the same cost | A migration rebuilds that model's index, inside this change, per the requirements' acceptance criterion for it |
| A different **family** wins | The change stops: ADR-002 records the finding, the roadmap gains a row, and the swap is proposed on its own — it reopens the narrowed-search contract (decision 8) and is not a parameter change |

### 10. What CI keeps

Timings on a shared runner measure the runner, so no timing is asserted. What
the integration suite asserts is what stays true on any machine: the ground
truth's plan has no index scan; the recall figure falls below 1 when the index
is deliberately asked to look less far than the ranking needs (a measurement
that cannot report a miss is worthless); recall at the default effort clears the
bound with margin on a corpus small enough to build in seconds; and the
published command leaves a populated store untouched, its schema gone. The
10 000-per-model run that the document and the ADR quote is an operator command,
run by hand, its output pasted with the machine it ran on.

## Risks / Trade-offs

- **An HNSW build is not bit-identical between runs** (graph construction
  depends on insertion order and concurrency) → the corpus is seeded and
  inserted in one order, the CI threshold is set with margin below the published
  figure, and the document says its numbers are one run on one machine, as
  change 12's already does.
- **A synthetic distribution is not the service's distribution** → stated in the
  document, with the direction of the bias named (a clustered real corpus is
  easier for an ANN index than this one, so the measured recall is a floor, not
  a promise); the demo corpus's size is given as the reason it cannot stand in.
- **The refactor could weaken the guard that protects the store** → the guard's
  tests keep running the published `filter_benchmark.py` end to end with their
  assertions unchanged, and the new command is put through the same battery;
  both then exercise the one module. Gate 2 reads that diff.
- **The command is slow enough to be annoying** (building four indexes over two
  models) → `--assets` and `--queries` are options, the default is the size the
  requirement names, and the document states the wall time of the published run.
- **`ivfflat.probes` and `lists` chosen from memory would be wrong** → both come
  from the installed pgvector's documentation, checked at implementation time,
  and the values used are printed with the results.
- **A recall test in CI could become flaky** → it is the only performance-shaped
  assertion, it runs on a small seeded corpus, and its threshold has margin; if
  it ever flaps, the honest fix is to lower the threshold and say so, not to
  delete the test.

## Migration Plan

No schema change is planned. If decision 9's third row materialises, the
migration is an ordinary Alembic revision that drops and recreates one model's
partial index; it rewrites no rows, `downgrade()` restores the previous
parameters, and `tests/integration/test_migration_roundtrip.py` covers the round
trip that already exists.

## Open Questions

None that change the specs, the approach or the tasks. What the numbers will say
is the question this change exists to answer, and decision 9 already fixes what
happens for each answer.
