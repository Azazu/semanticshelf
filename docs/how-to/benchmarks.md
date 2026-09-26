# Benchmarks

Two measurements live on this page, each with a command that produces it.

- **[The plan a narrowed search takes](#the-plan-a-narrowed-search-takes)** —
  which of three ways PostgreSQL answers a search that narrows by a tag or by
  metadata, and which of them can come back short (change 12).
- **[What the index approximates](#what-the-index-approximates)** — how much of
  the true ranking the vector index returns, what it costs, and how HNSW and
  IVFFlat compare per model (change 14; the decision is
  [ADR-002](../adr/ADR-002-vector-index-family-and-parameters.md)).

Both build their corpus in a schema of their own, inside the database
`DATABASE_URL` names, and drop only what they created. Neither can touch the
tables the service uses: that promise is one module (`scripts/bench_schema.py`)
both commands import, and the integration suite runs each published command
against a populated store and checks that every row is still there.

## The plan a narrowed search takes

A search that narrows by a tag or by metadata is one query, and PostgreSQL has
more than one way to answer it. Which way it picks decides whether the answer
can come back short — so the choice is measured rather than assumed, and this
is the command that measures it.

```console
$ uv run python scripts/filter_benchmark.py --assets 3000 --seed 7
```

It builds a synthetic corpus — one vector per asset, planar, so the ranking is
arithmetic a reader can check — and runs the service's own statement over it,
per selectivity, at `hnsw.iterative_scan` off and `strict_order`, with the
planner's statistics fresh and without them. Synthetic on purpose: what is
measured is the planner's choice against selectivity, and a real model's vectors
would add a variable nobody can control.

**It cannot touch your store, and it deletes only what it created.** The corpus
is built in a schema of its own, inside the database `DATABASE_URL` names, and
that schema is created by the run: a name that is already taken is a refusal,
never a drop, so pointing the script at an existing schema cannot destroy it.
The cleanup at the end drops that schema only if the create succeeded. The
tables are copied from the service's own (`LIKE ... INCLUDING ALL`), so the
indexes measured are the indexes a request meets; before a single row is
written, the script checks that every unqualified name resolves inside its own
schema and refuses to run if it does not; and `public`, the `pg_*` schemas and
anything outside `^[a-z_][a-z0-9_]{0,48}$` are refused at the command line.
Integration tests run the published command against a populated store and assert
that every asset, embedding and job is still there, and that an occupied schema
name is refused with its contents intact.

Add `--plans` to print one full plan per shape, and `--schema <name>` to build
somewhere other than `filter_benchmark` — a name nothing else is using.

### What one run says

Corpus: 3000 assets, one vector each of `clip-vit-l14`, seed 7. Page: limit 20, so 21 rows are asked for, at `hnsw.ef_search` 40.

| matches | statistics | iterative_scan | plan | rows of asked | ms |
|---|---|---|---|---|---|
| 1 in 2 | none | off | vector index | 21 of 21 | 1.2 |
| 1 in 2 | none | strict_order | vector index | 21 of 21 | 1.2 |
| 1 in 5 | none | off | vector index | 8 of 21 | 0.8 |
| 1 in 5 | none | strict_order | vector index | 21 of 21 | 1.5 |
| 1 in 20 | none | off | vector index | 1 of 21 | 0.5 |
| 1 in 20 | none | strict_order | vector index | 21 of 21 | 1.7 |
| 1 in 100 | none | off | vector index | 0 of 21 | 0.4 |
| 1 in 100 | none | strict_order | vector index | 21 of 21 | 4.8 |
| 1 in 300 | none | off | vector index | 0 of 21 | 0.4 |
| 1 in 300 | none | strict_order | vector index | 10 of 21 | 4.9 |
| 1 in 2 | fresh | off | vector index | 21 of 21 | 0.2 |
| 1 in 2 | fresh | strict_order | vector index | 21 of 21 | 0.2 |
| 1 in 5 | fresh | off | sequential scan | 21 of 21 | 1.5 |
| 1 in 5 | fresh | strict_order | sequential scan | 21 of 21 | 1.3 |
| 1 in 20 | fresh | off | sequential scan | 21 of 21 | 0.7 |
| 1 in 20 | fresh | strict_order | sequential scan | 21 of 21 | 0.8 |
| 1 in 100 | fresh | off | sequential scan | 21 of 21 | 0.5 |
| 1 in 100 | fresh | strict_order | sequential scan | 21 of 21 | 0.5 |
| 1 in 300 | fresh | off | exact, narrowed rows | 10 of 21 | 0.3 |
| 1 in 300 | fresh | strict_order | exact, narrowed rows | 10 of 21 | 0.3 |

Rows are what the page asked for against what came back — 21, because a page of
20 reads one row beyond itself to say whether more exist. Where the store holds
fewer matches than that, the answer is complete at fewer: 1 in 300 over 3 000
assets is 10 matching assets, so 10 of 21 is the whole ranking.

The times are one machine, one run, a corpus that fits in memory; they are there
to compare the plans with each other, not to predict a deployment.

### Reading it

**Three plans answer one query.** With no statistics the planner uses the vector
index: an HNSW scan in distance order, joined to the narrowed `assets` rows.
Given statistics, it leaves the index for anything more selective than 1 in 2 —
on a corpus this size, reading every vector of the model and sorting is simply
cheaper, and for 1 in 300 it drives from the narrowed assets and computes their
distances exactly. All three answer the same question; only the first is
approximate, and only the first can stop early.

**On the index path, the iterative scan is the whole difference.** With
`hnsw.iterative_scan` off, the scan chooses its candidates once — `ef_search` of
them — and the narrowing then removes most of them: 8 of 21 at 1 in 5, one at
1 in 20, and **nothing at all** at 1 in 100 while thirty matching assets sit
just past the candidate window. That is the defect this whole change exists to
prevent, and it is not a bad ranking but an empty page. With `strict_order` the
scan keeps going — until the page is filled, until the index is exhausted, or
until `hnsw.max_scan_tuples` (20 000 by default) stops it, which is the bound
`scan_limited` reports — and the same queries come back full. The service
therefore sets `strict_order` for every narrowed query and leaves it off
otherwise.

**Statistics decide which plan, and stale statistics are a real state.** A table
freshly written — a restored dump, a bulk import, a corpus built by a demo
script — has none, and every one of those queries takes the index path where the
scan's budget applies. `ANALYZE` after a bulk load is therefore not tidiness: it
is what lets the planner pick the exact plan when the narrowing is selective.

**Only the index path can be cut short**, and when it is, the answer says so.
The service reports `scan_limited` when the scan reached fewer rows than the
answer needed while more matching rows exist. The other two plans read every
candidate they need by construction and never set it.

**What this means for a deployment.** A corpus of thousands is small enough that
reading every vector wins; a corpus of millions is not, and the index path — the
one with the bound — becomes the common one. Two things follow: run `ANALYZE`
after a bulk load, and treat `scan_limited` as a real answer a client sees, not
a corner case. A narrowing that matches very little, very deep in the ranking,
is the shape that reaches the bound.

### The plans in full

The query vector is 768 zeros with a one in front; it is written `<query>` here.

#### vector index — 1 in 2, statistics none, iterative_scan off

```text
Limit  (cost=115.11..115.15 rows=2 width=24)
  ->  Incremental Sort  (cost=115.11..115.15 rows=2 width=24)
        Sort Key: (((embeddings.vector)::vector(768) <=> <query>)), embeddings.asset_id
        Presorted Key: (((embeddings.vector)::vector(768) <=> <query>))
        ->  Limit  (cost=50.83..115.10 rows=1 width=24)
              ->  Nested Loop  (cost=50.83..115.10 rows=1 width=24)
                    Join Filter: (assets.id = embeddings.asset_id)
                    ->  Index Scan using embeddings_vector_idx on embeddings  (cost=4.01..48.13 rows=12 width=48)
                          Order By: ((vector)::vector(768) <=> <query>)
                    ->  Materialize  (cost=46.82..65.90 rows=6 width=16)
                          ->  Bitmap Heap Scan on assets  (cost=46.82..65.87 rows=6 width=16)
                                Recheck Cond: (tags @> '{every_2}'::text[])
                                ->  Bitmap Index Scan on assets_tags_idx  (cost=0.00..46.82 rows=6 width=0)
                                      Index Cond: (tags @> '{every_2}'::text[])
```

#### sequential scan — 1 in 5, statistics fresh, iterative_scan off

```text
Limit  (cost=224.58..225.56 rows=21 width=24)
  ->  Incremental Sort  (cost=224.58..225.56 rows=21 width=24)
        Sort Key: (((embeddings.vector)::vector(768) <=> <query>)), embeddings.asset_id
        Presorted Key: (((embeddings.vector)::vector(768) <=> <query>))
        ->  Limit  (cost=224.56..224.62 rows=21 width=24)
              ->  Sort  (cost=224.56..226.06 rows=600 width=24)
                    Sort Key: (((embeddings.vector)::vector(768) <=> <query>))
                    ->  Hash Join  (cost=122.00..208.39 rows=600 width=24)
                          Hash Cond: (embeddings.asset_id = assets.id)
                          ->  Seq Scan on embeddings  (cost=0.00..75.50 rows=3000 width=34)
                                Filter: (model = 'clip-vit-l14'::text)
                          ->  Hash  (cost=114.50..114.50 rows=600 width=16)
                                ->  Seq Scan on assets  (cost=0.00..114.50 rows=600 width=16)
                                      Filter: (tags @> '{every_5}'::text[])
```

#### exact, narrowed rows — 1 in 300, statistics fresh, iterative_scan off

```text
Limit  (cost=151.39..151.85 rows=10 width=24)
  ->  Incremental Sort  (cost=151.39..151.85 rows=10 width=24)
        Sort Key: (((embeddings.vector)::vector(768) <=> <query>)), embeddings.asset_id
        Presorted Key: (((embeddings.vector)::vector(768) <=> <query>))
        ->  Limit  (cost=151.37..151.40 rows=10 width=24)
              ->  Sort  (cost=151.37..151.40 rows=10 width=24)
                    Sort Key: (((embeddings.vector)::vector(768) <=> <query>))
                    ->  Nested Loop  (cost=47.12..151.21 rows=10 width=24)
                          ->  Bitmap Heap Scan on assets  (cost=46.84..76.15 rows=10 width=16)
                                Recheck Cond: (tags @> '{every_300}'::text[])
                                ->  Bitmap Index Scan on assets_tags_idx  (cost=0.00..46.84 rows=10 width=0)
                                      Index Cond: (tags @> '{every_300}'::text[])
                          ->  Index Scan using embeddings_asset_id_model_key on embeddings  (cost=0.28..7.50 rows=1 width=34)
                                Index Cond: ((asset_id = assets.id) AND (model = 'clip-vit-l14'::text))
```

## What the index approximates

Every search the service answers is approximate: an HNSW scan returns the
neighbours it found, not provably the nearest ones. This is the command that
says by how much, per model, and what the alternative index family would cost
instead.

```console
$ uv run python scripts/index_benchmark.py --assets 10000 --seed 7
```

It builds a corpus per model — 10 000 unit vectors scattered around 64 seeded
centroids — then an exact ranking to grade against, then each index one at a
time, and reports what each one gives and what it cost. `--queries` (at most
50), `--seed` and `--schema` are the other options; the published run above
takes about twenty-six seconds on one laptop and holds its corpus in memory as
text while it writes it, which is what bounds the size published here.

**Why a synthetic corpus, and why clustered.** What is compared is two index
families over one distribution, and a real model's vectors would add a variable
nobody can hold still between runs. Uniform vectors would not do either: in 768
dimensions a uniform sample of the sphere has no neighbours to find — every pair
is nearly orthogonal — so recall over it would measure how an index broke a
near-tie. A corpus with no neighbours cannot be asked a nearest-neighbour
question at all, so this one is built with them — around seeded centroids, with
the two constants that say how tightly printed beside the results. How that
compares with a real embedding distribution, in either direction, is not
something this measurement can say.

**Why not the demo corpus.** `demo-dataset download` takes at most a few hundred
pictures. At that size a scan with `ef_search` 40 visits a sizeable fraction of
the graph and returns the exact ten every time: recall is 1 by construction and
tells you nothing about the index. The corpus here is the size NFR-PERF-1 names.

**How the figures are made.**

- **The ranking it grades against is exact.** The corpus is loaded into a table
  with no index at all, the ground truth is read with index scans switched off,
  and the plan of that statement is checked: a ground truth produced by the
  index it grades would report a perfect score for everything and look like
  success.
- **One index at a time.** Every other index is dropped, so the plan has nothing
  else to choose and the figures belong to the index named — checked, per
  configuration, by reading the plan. Sequential scans are switched off for the
  measuring transaction, because what is measured here is what the index gives
  up rather than whether a planner would pick it on a corpus this size (that is
  the section above).
- **The shipped index is the migration's own.** The tables are copied
  `LIKE ... INCLUDING ALL`, so the HNSW index measured is the one a request
  meets, at the parameters `0002_asset_schema` states. Only the alternatives are
  declared by the script.
- **recall@10** is `|the index's ten ∩ the true ten| / 10`, averaged over the 50
  queries, with the worst single query beside it: a mean of 0.97 hiding one
  query at 0.4 is the shape that matters to somebody's search. NFR-PERF-4's
  0.95 is a bound on that **mean**; the worst query is published, not bounded,
  because over ten neighbours a per-query 0.95 would mean all ten of them every
  time.
- **p95** is the nearest-rank percentile of the 50 timings — the 48th smallest —
  warm, and excludes embedding the query, as NFR-PERF-1 does.

### What one run says

Corpus: 10 000 assets, one vector per asset for every model, seed 7; 64
centroids, spread 0.5, unit length. 50 queries from the same centres, none of
them stored. Page: limit 20, so 21 rows are asked for; the service's own effort
for it is `hnsw.ef_search` 40, and it sets no `ivfflat.probes` at all, so a
deployment runs IVFFlat at pgvector's default of 1. pgvector 0.8.5 on PostgreSQL
16.14.

**`clip-vit-l14` (768 dimensions)**

| index | parameters | build | size | at | recall@10 | worst | p95 ms |
|---|---|---|---|---|---|---|---|
| hnsw shipped | m = 16, ef_construction = 64 | 1.5 s | 39.1 MB | ef_search 40 | 1.000 | 1.00 | 1.6 |
| hnsw wider | m = 32, ef_construction = 128 | 4.4 s | 39.1 MB | ef_search 40 | 1.000 | 1.00 | 1.0 |
| ivfflat lists 10 | lists = 10 | 0.2 s | 39.1 MB | probes 1 | 1.000 | 1.00 | 1.5 |
| ivfflat lists 100 | lists = 100 | 0.3 s | 39.6 MB | probes 1 | 0.860 | 0.20 | 1.0 |

| index | setting | recall@10 | worst | p95 ms |
|---|---|---|---|---|
| hnsw shipped | ef_search 20 | 0.996 | 0.90 | 1.0 |
| hnsw shipped | ef_search 40 | 1.000 | 1.00 | 1.6 |
| hnsw shipped | ef_search 80 | 1.000 | 1.00 | 1.2 |
| hnsw shipped | ef_search 120 | 1.000 | 1.00 | 0.8 |
| hnsw shipped | ef_search 200 | 1.000 | 1.00 | 2.3 |
| hnsw wider | ef_search 20 | 1.000 | 1.00 | 0.9 |
| hnsw wider | ef_search 200 | 1.000 | 1.00 | 2.2 |
| ivfflat lists 10 | probes 1 | 1.000 | 1.00 | 1.5 |
| ivfflat lists 10 | probes 3 | 1.000 | 1.00 | 3.0 |
| ivfflat lists 10 | probes 10 | 1.000 | 1.00 | 9.3 |
| ivfflat lists 100 | probes 1 | 0.860 | 0.20 | 1.0 |
| ivfflat lists 100 | probes 2 | 0.984 | 0.70 | 1.2 |
| ivfflat lists 100 | probes 5 | 1.000 | 1.00 | 0.9 |
| ivfflat lists 100 | probes 20 | 1.000 | 1.00 | 2.1 |

**`dinov2-large` (1024 dimensions)**

| index | parameters | build | size | at | recall@10 | worst | p95 ms |
|---|---|---|---|---|---|---|---|
| hnsw shipped | m = 16, ef_construction = 64 | 1.8 s | 78.1 MB | ef_search 40 | 1.000 | 1.00 | 1.2 |
| hnsw wider | m = 32, ef_construction = 128 | 5.2 s | 78.1 MB | ef_search 40 | 1.000 | 1.00 | 2.3 |
| ivfflat lists 10 | lists = 10 | 0.2 s | 78.2 MB | probes 1 | 1.000 | 1.00 | 2.2 |
| ivfflat lists 100 | lists = 100 | 0.4 s | 78.9 MB | probes 1 | 0.866 | 0.40 | 1.1 |

| index | setting | recall@10 | worst | p95 ms |
|---|---|---|---|---|
| hnsw shipped | ef_search 20 | 0.996 | 0.80 | 1.8 |
| hnsw shipped | ef_search 40 | 1.000 | 1.00 | 1.2 |
| hnsw shipped | ef_search 80 | 1.000 | 1.00 | 1.6 |
| hnsw shipped | ef_search 120 | 1.000 | 1.00 | 1.2 |
| hnsw shipped | ef_search 200 | 1.000 | 1.00 | 2.1 |
| hnsw wider | ef_search 20 | 1.000 | 1.00 | 1.0 |
| hnsw wider | ef_search 200 | 1.000 | 1.00 | 3.8 |
| ivfflat lists 10 | probes 1 | 1.000 | 1.00 | 2.2 |
| ivfflat lists 10 | probes 3 | 1.000 | 1.00 | 3.0 |
| ivfflat lists 10 | probes 10 | 1.000 | 1.00 | 11.7 |
| ivfflat lists 100 | probes 1 | 0.866 | 0.40 | 1.1 |
| ivfflat lists 100 | probes 2 | 0.990 | 0.70 | 1.4 |
| ivfflat lists 100 | probes 5 | 1.000 | 1.00 | 1.5 |
| ivfflat lists 100 | probes 20 | 1.000 | 1.00 | 2.9 |

The curves above are the full output with the middle steps of the flat rows left
out; the command prints every step.

A narrowing that matches one asset in a hundred — 100 of the 10 000 — filled its
page under every index: 21 of 21, HNSW at `strict_order`, IVFFlat at
`relaxed_order`, which is the strictest each family has.

### Reading it

**The shipped index gives up nothing measurable at this size.** recall@10 is
1.000 for both models at the effort the service sets, no single query below
1.00, and p95 is 1.6 ms and 1.2 ms against NFR-PERF-1's bound of 100 ms. The
first miss appears one step *below* the default, at `ef_search` 20 (0.996 mean,
worst query 0.90): the default has margin rather than luck.

**Neither alternative earns the change.** A wider HNSW (`m = 32`,
`ef_construction = 128`) costs about three times the build for the same recall
and the same size. IVFFlat at pgvector's own guidance for this many rows
(`lists = rows / 1000` = 10) also returns everything — because ten lists over
ten thousand vectors means one probe reads a thousand of them, which is closer
to a scan than to an index, and its p95 climbs steeply as probes are added
(9.3 ms at ten probes, since probing *is* reading). At the finer partitioning a
larger corpus would need (`lists = sqrt(rows)` = 100), IVFFlat at its default of
one probe returns 0.86 of the ranking with one query down at 0.20, and needs
five probes to match what HNSW gives at its default.

**One difference is structural rather than numerical.** `hnsw.iterative_scan`
accepts `strict_order`; `ivfflat.iterative_scan` does not — the database refuses
the value, and the command reports what it accepted rather than what anyone
remembered. The service's narrowed search is built on that strict order (the
section above), so the two families are not interchangeable even where their
numbers are.

**How much of this is one run.** Repeating the same command: HNSW's recall
figures are identical, timings move by about a millisecond, and IVFFlat at
`lists = 100` moved from 0.860 to 0.908 — its lists come from a k-means over a
sample, so a rebuild is a different partition. Treat the timings as a comparison
between rows, not as a prediction for a deployment.

**What this measurement does not reach.** Ten thousand vectors per model is
small for an approximate index: this is the size the requirements name and the
size this project targets, and at it the approximation barely bites. The part of
the curve where `ef_search` decides recall is at millions of vectors, on a
machine with the memory for that index. This corpus is also not a model's: it
is 64 seeded centroids with a stated spread, and whether a real embedding space
is kinder or harsher to either index family is not measured anywhere here.
What the numbers support is a decision for this project at this size — which is
what
[ADR-002](../adr/ADR-002-vector-index-family-and-parameters.md) records, limits
included.
