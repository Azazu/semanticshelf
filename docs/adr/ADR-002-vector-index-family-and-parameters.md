# ADR-002: HNSW at m = 16, ef_construction = 64 stays, measured against IVFFlat

**Date:** 2026-09-25
**Status:** accepted
**Related:** ADR-001 (the storage layout, which left this open); authored by the OpenSpec change `tune-vector-indexes`

## Context

ADR-001 chose one partial HNSW cosine index per model over the dimension cast,
built with `m = 16` and `ef_construction = 64`, and said outright what it did not
choose: whether HNSW is the right family at all, whether those build parameters
are right, and what recall the defaults actually give. The requirements have
carried the shape of that answer since they were written — NFR-PERF-1 (p95 ≤ 100
ms for `limit = 20` over 10 000 embeddings per model, the query embedding
excluded) and NFR-PERF-4 (recall@10 ≥ 0.95 against an exact scan at the default
effort, with the `ef_search` 20 → 200 curve recorded) — and pointed both at this
record.

Until now every search this service answered was approximate by an unknown
amount. `scripts/index_benchmark.py` is the command that measures it, and
[`docs/how-to/benchmarks.md`](../how-to/benchmarks.md) carries the run these
numbers come from: pgvector 0.8.5 on PostgreSQL 16.14, 10 000 unit vectors per
model around 64 seeded centroids, 50 queries from the same distribution and none
of them stored, an exact ranking read with no index in existence and its plan
checked, every index measured alone on the table with its plan read.

| index | build | size (768) | at the shipped setting | recall@10 | worst query | p95 |
|---|---|---|---|---|---|---|
| **HNSW `m = 16, ef_construction = 64`** | 1.5 s | 39.1 MB | `ef_search` 40 | **1.000** | 1.00 | **1.6 ms** |
| HNSW `m = 32, ef_construction = 128` | 4.4 s | 39.1 MB | `ef_search` 40 | 1.000 | 1.00 | 1.0 ms |
| IVFFlat `lists = 10` (pgvector's guidance at this size) | 0.2 s | 39.1 MB | `probes` 1 | 1.000 | 1.00 | 1.5 ms |
| IVFFlat `lists = 100` (`sqrt(rows)`) | 0.3 s | 39.6 MB | `probes` 1 | 0.860 | 0.20 | 1.0 ms |

`dinov2-large` at 1024 dimensions gives the same ordering: 1.000 at `ef_search`
40 with p95 1.2 ms for the shipped index, 0.866 for IVFFlat at `lists = 100` and
one probe. The `ef_search` curve is flat at 1.000 from 40 to 200 and first
shows a miss at 20 (0.996, worst query 0.90) — for both models.

Two further measurements decided more than the table did:

- **`ivfflat.iterative_scan` has no `strict_order`.** The database refuses the
  value; `hnsw.iterative_scan` accepts it. Change 12 built the narrowed-search
  contract on exactly that strict order: a narrowed query keeps scanning in
  distance order until the page is filled or a stated bound stops it, and the
  answer reports `scan_limited` when it was the bound.
- **IVFFlat's partitions are not stable across builds.** Repeating the run moved
  `lists = 100` at one probe from 0.860 to 0.908, because its lists come from a
  k-means over a sample. HNSW's recall figures were identical between runs.

## Decision

**HNSW stays, per model, at `m = 16` and `ef_construction = 64`, with
`HNSW_EF_SEARCH` 40 as the default effort.** Nothing in the service changes;
what changes is that the configuration is now measured rather than inherited,
and `0002_asset_schema` remains the migration that states it.

The measurement is part of the decision, not a one-off: `scripts/index_benchmark.py`
is published, seeded and reproducible, the store's specification requires the
figure to exist and to clear 0.95 at the default effort, and the integration
suite keeps the parts of it that are deterministic — an exact ground truth, a
recall figure that can report a miss, and the bound cleared on a corpus CI can
build.

**What this decision assumes.** A corpus of the order of ten thousand vectors
per model, on one machine, over a clustered distribution. At that size the
approximation barely bites, which is *why* the defaults hold; it is not evidence
that they hold at a hundred times the size.

**What it does not guarantee.** Not that HNSW returns the exact ranking — it
returns 1.000 of it here, and 0.996 at `ef_search` 20, which is the same
statement as "this is approximate and the effort is what buys it back". Not a
latency for a deployment: the timings are one laptop, one run, a corpus in
memory. And not a recall figure for real CLIP or DINOv2 vectors: the corpus is
synthetic on purpose, and the direction of the difference is not established
here.

## Alternatives considered

**IVFFlat at `lists = rows / 1000`** — pgvector's own guidance for a corpus of
this size, and the cheapest index to build (0.2 s against 1.5 s). It lost on
what that number means at this scale: ten lists over ten thousand vectors makes
one probe read a thousand of them, so its recall of 1.000 is bought by reading a
tenth of the corpus, and its p95 climbs to 9.3 ms at ten probes where HNSW stays
near one. It is a scan with extra steps until the corpus is much larger.

**IVFFlat at `lists = sqrt(rows)`** — the partitioning a larger corpus would
want. It lost on recall at the setting a deployment would actually run: 0.860
with one query at 0.20, against a requirement of 0.95, and it needs five probes
to match what HNSW gives at its default. It also loses structurally: no
`strict_order`, so adopting it would reopen the narrowed-search contract of
change 12 and the `scan_limited` report that rests on it.

**HNSW at `m = 32, ef_construction = 128`** — three times the build time for the
same recall and the same index size, on a corpus where recall is already 1.000.
There is nothing for it to buy back. It is the first thing to re-measure if the
corpus grows by orders of magnitude, since that is where a denser graph earns
its build cost.

**Raising or lowering `HNSW_EF_SEARCH`.** Raising it buys nothing measurable
here (the curve is flat from 40 upwards) and costs latency at the deep pages
where the service already raises it per request. Lowering it to 20 puts the
first miss inside the default (0.996 mean, one query at 0.90) for a saving
inside the noise of these timings. 40 — pgvector's own default — is kept.

## Consequences

- No migration, no setting change, no code change: the store's index is what it
  was, and the difference is that the numbers exist and are reproducible.
- The narrowed-search contract of change 12 is now also an argument about the
  index family: adopting IVFFlat would break `strict_order` and reopen it. That
  is recorded here so a future change does not discover it by regression.
- `scripts/index_benchmark.py` is a published command with the same promise as
  the filter benchmark: it builds in a schema of its own, drops only what it
  created, and cannot touch the service's tables — one shared guard, exercised
  through both commands by the integration suite.
- The measurement's own limits are the reopening conditions. This record should
  be revisited when the corpus reaches a scale where HNSW's graph is not
  effectively exhaustive (a million vectors per model is the natural next size),
  when a model with a much wider vector arrives, or when pgvector changes what
  its iterative scans promise.
- The benchmark holds its corpus in memory as text while it writes it, which is
  what bounds the published size. Measuring a million vectors means streaming
  the corpus into the copy — a change to the command, not to this decision.

## Supersedes

No ADR clause. ADR-001 deferred this question to this record and is otherwise
unchanged.
