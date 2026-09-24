# Measure a narrowed vector search

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

**It cannot touch your store.** The corpus is built in a schema of its own,
created and dropped by the run, inside the database `DATABASE_URL` names. The
tables are copied from the service's own (`LIKE ... INCLUDING ALL`), so the
indexes measured are the indexes a request meets; before a single row is
written, the script checks that every unqualified name resolves inside that
schema and refuses to run if it does not. An integration test runs the command
above against a populated store and asserts that every row is still there.

Add `--plans` to print one full plan per shape, and `--schema <name>` to build
somewhere other than `filter_benchmark`.

## What one run says

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

## Reading it

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

## The plans in full

The query vector is 768 zeros with a one in front; it is written `<query>` here.

### vector index — 1 in 2, statistics none, iterative_scan off

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

### sequential scan — 1 in 5, statistics fresh, iterative_scan off

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

### exact, narrowed rows — 1 in 300, statistics fresh, iterative_scan off

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
