# Benchmarks

Four measurements live on this page, each with a command that produces it.

- **[The plan a narrowed search takes](#the-plan-a-narrowed-search-takes)** —
  which of three ways PostgreSQL answers a search that narrows by a tag or by
  metadata, and which of them can come back short (change 12).
- **[What the index approximates](#what-the-index-approximates)** — how much of
  the true ranking the vector index returns, what it costs, and how HNSW and
  IVFFlat compare per model (change 14; the decision is
  [ADR-002](../adr/ADR-002-vector-index-family-and-parameters.md)).
- **[What a query in another language costs](#what-a-query-in-another-language-costs)**
  — how well the multilingual query encoder answers, against the corpus's own
  labels and against the English page (change 17; the decision is
  [ADR-005](../adr/ADR-005-multilingual-query-encoder.md)).
- **[Does a style key answer something the keys here do not?](#does-a-style-key-answer-something-the-keys-here-do-not)**
  — whether a style descriptor separates *how a picture looks* from *what is in
  it* better than the two keys already stored do (change 18; the decision is
  [ADR-006](../adr/ADR-006-style-as-a-third-key.md)).

The first two build their corpus in a schema of their own, inside the database
`DATABASE_URL` names, and drop only what they created. Neither can touch the
tables the service uses: that promise is one module (`scripts/bench_schema.py`)
both commands import, and the integration suite runs each published command
against a populated store and checks that every row is still there. The third
builds nothing at all — it measures a model against the corpus that is already
there, so it reads in a transaction it declares read-only. The fourth touches
no database of any kind: its corpus is files, built by the command itself.

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

## What a query in another language costs

The service's text tower was trained on English captions, and FR-TXT-5 made
that a boundary: other languages degrade toward a random ranking. Change 17
adds a **query encoder** — a multilingual text tower trained to land in the
same image space — and §9 of the specification allows lifting the boundary
"only with numbers". These are the numbers.

```console
$ uv run python scripts/multilingual_benchmark.py --languages en,ru,de,fr,es
```

It needs a corpus in the store: the 500-picture demo sample, indexed with
`clip-vit-l14`, is what the run below used (`make demo`, or `index-folder
.data/demo/pictures --recursive`).

### What it measures, and against what

Ground truth is the corpus itself. Each picture of the demo sample carries
COCO's own labels as tags, so a concept — `zebra`, `traffic light`, `teddy
bear` — has a set of pictures that carry it, and a query naming that concept in
some language either finds them or does not.

- **recall@10**: of the pictures carrying the tag, how many reached the first
  ten. Recall rather than precision, because precision@10 is capped at
  `relevant/10` for a concept the corpus holds four pictures of — a perfect
  answer would score 0.4 and read as a failure.
- **agreement@10**: how much of the *English* page the same concept in another
  language brings back. It is published without a bound: a different page of
  the same quality is not a failure, and no threshold on it would have meant
  anything before the first measurement.

The concept set is chosen by rules that look at no language's results: a tag
carried by 3 to 10 assets, at least 20 such concepts, and the English baseline
itself clearing recall 0.5 — a set the service's own model cannot answer would
measure the corpus rather than any encoder, and the run says so and stops.

Ranking is **exact**, in memory. What the index gives up is the measurement
above; mixing the two would leave a reader unable to tell which one moved.

### What one run says

Corpus: 500 assets with a `clip-vit-l14` vector. Concepts: 21 tags carried by
3–10 assets each. Encoder `M-CLIP/XLM-Roberta-Large-Vit-L-14` at revision
`40afa80a85e8efa990384a24bbe5a1f6f1cc81b5`, architecture config at
`c23d21b0620b635a76227c604d44e43a9f0ee389`. A language is claimed at mean
recall@10 ≥ 0.5 **and** ≥ 0.8 × the English baseline.

| language | asked by | mean recall@10 | worst concept | mean agreement@10 | claimed |
|---|---|---|---|---|---|
| en | `clip-vit-l14` | 0.649 | apple 0.000 | 1.000 | baseline |
| en | `mclip-xlmr-l14` | 0.683 | apple 0.000 | 0.857 | yes |
| ru | `mclip-xlmr-l14` | 0.684 | apple 0.000 | 0.843 | yes |
| de | `mclip-xlmr-l14` | 0.665 | apple 0.000 | 0.843 | yes |
| fr | `mclip-xlmr-l14` | 0.683 | apple 0.000 | 0.871 | yes |
| es | `mclip-xlmr-l14` | 0.659 | apple 0.000 | 0.857 | yes |

The 21 concepts, with how many assets carry each tag: zebra 9, elephant 10,
giraffe 5, sheep 4, cow 7, bicycle 9, airplane 5, stop-sign 3, fire-hydrant 8,
suitcase 7, frisbee 7, snowboard 8, kite 8, wine-glass 6, banana 8, apple 3,
orange 6, donut 6, book 10, vase 10, teddy-bear 6. The run prints them with the
phrase used in each language, because a measurement whose inputs are hidden is
an opinion.

### Reading it

**The four languages clear both bounds**, by a distance: every one is within
three points of the English baseline, and three of them are above it.

**The interesting row is the second one.** Asked in *English*, the encoder
scores 0.683 against the baseline's 0.649 and agrees with it on 0.857 of the
page — about as much as the other languages do. So the difference between the
pages is not what a translation costs: it is that this is a **different text
tower**, which answers slightly differently and, on this corpus and these
concepts, slightly better. A reader who expected "English is the real one and
the rest are approximations" gets a more interesting fact instead.

**The worst concept is the same everywhere**: `apple`, at 0.000, in every
language including the baseline. Three pictures carry that tag and no tower
surfaces them, which says something about the label or the pictures rather than
about any language.

**What this does not say.** Nothing about the other 44 languages the encoder
accepts — they are untested here. Nothing about queries that are not a concept
name: a sentence, a mood, a proper noun. Nothing about a corpus other than this
one; a claim about somebody's own pictures needs their own run of the same
command. And nothing about how the *index* behaves for these queries, which is
the measurement above.


## Does a style key answer something the keys here do not?

The roadmap asked for a style embedding as a third key. A key is permanent — it
is part of an embedding's identity, it takes a value in the schema's allowlist,
it costs an index and a vector for every asset, and it queues work for every
upload — and this service already stores image vectors under two keys that both
rank pictures by something neighbouring style. So change 18 asked the question
first, and `embedding-models` now carries the rule it followed: a key earns its
place by a published, re-runnable measurement against **every** key of its kind,
with a bound fixed before the numbers are seen.

```console
$ uv run --group style python scripts/style_benchmark.py --pictures 100
```

It needs the `style` dependency group, which nothing installs implicitly
(`uv sync` leaves it out and the service image cannot carry it). It reads no
database, writes nothing anywhere, and prints its progress because three model
passes over several hundred pictures on a CPU take minutes per model. On a
laptop that has other work to do, `TORCH_NUM_THREADS=4 nice -n 19` in front of
it keeps the machine responsive at the cost of wall-clock time.

**What it prints so a second run can be compared with this one.** A digest over
the corpus's file names and bytes — "the first hundred pictures of a folder" is
not something a reader can obtain, and the digest is what two runs compare to
find out whether they measured the same pictures. That part is exact.

The checkpoint table beside it is **not**, and the command says so above it.
Only the candidate is pinned by this repository. The two stored keys load a
checkpoint *name* a deployment configures, with no revision, and each adapter
resolves its weights and its processor in two separate calls — so a scan of the
model cache afterwards reads whatever that name points at now, not what either
call read. Two runs whose rows match may still have loaded different weights.
The table is a thread to pull when numbers disagree, not evidence that they
should agree; pinning those two keys is a change to the service
(`openspec/ROADMAP.md`, row 20).

### The corpus is built, not found

A corpus of paintings would be the natural thing to measure on, and this project
cannot have one: WikiArt's licence is `unknown`, and change 9 set the rule that
only licences permitting reuse are taken, because the service re-encodes a
thumbnail and that is a derivative work.

So the command builds its corpus from the pictures already here, by applying six
deterministic looks to each photograph of a folder — the picture untouched,
grayscale, posterised, edges, painterly, sepia. Every look is a pure function of
the bytes, so two images share a look because the same function produced them
and share a subject because they came from the same photograph: a ground truth
nobody has to label, and one a re-run rebuilds exactly.

Two rules keep a run from publishing a number it cannot stand behind. A look
that flattens a photograph to one colour keeps no subject, so that one
combination is dropped rather than measured — the rule reads the picture's
interior, because a 3x3 filter leaves the outermost ring untouched and a
flattened picture still carries its own frame. And a corpus below 20 photographs
or 4 looks is refused outright.

**These are filters, not painters.** What the measurement can support is a
statement about separating *how a picture looks* from *what is in it*, which is
the property a style key would be bought for. It is not evidence about
Impressionism; a claim about Impressionists needs Impressionists.

### The number that decides, and the one that only informs

Two statistics come out of the same vectors, and they can disagree.

- **Prefers the look** — the deciding one. Over every triple (an anchor, another
  photograph under the anchor's look, the anchor's photograph under another
  look), the fraction where the model scores the look-mate above the
  picture-mate, a tie counting a half. 0.5 is indifference.
- **The ratio of averages** — the diagnostic. Mean "same look, different
  picture" over mean "same picture, different look".

The ratio is the obvious statistic and it is the wrong one to decide on, because
a model's own similarity scale moves it. Models differ in how widely they spread
cosine similarity, and one whose scores all sit in a narrow high band scores well
on a ratio of two means while ranking the subject first every single time. A
ratio compares two population means; a search compares two candidates **against
the same anchor**. The preference is a proportion of a set the corpus fixes the
size of, so it has no zero denominator, no negative value, and no dependence on
that scale — and it survives any rescaling of the scores, which is what the
spec now requires of the number a bound is read on. The ratio is published
anyway, with `undefined` in place of a value wherever its denominator is not
positive, because seeing that the two disagree is worth more than not seeing it.

### The bound, fixed before the run

A candidate earns a key when its preference is **strictly greater** than

```text
incumbent + (1 - incumbent) / 2
```

where `incumbent` is the highest preference among the keys the service already
stores. Half the remaining distance to a perfect score is the only scale-free
way to say "decisively better" about a proportion: a multiplicative rule is
meaningless where `3 x 0.4` exceeds 1, and a fixed additive margin is easy
against a weak incumbent and unreachable against a strong one. One condition,
not two — the right-hand side is `(1 + incumbent) / 2` and a preference lies in
[0, 1], so a candidate that clears it has already been shown to prefer the look.

The measured keys are read from `app.domain`, not written out in the command, so
a key added to `EMBEDDING_MODELS` later cannot be left out of the comparison.


### What one run says

Corpus: 100 photographs of the demo sample under six looks — 600 images, none
refused as one colour, 297 000 triples, 29 700 pairs sharing a look and 1 500
sharing a picture, corpus digest `7a0f6d0a346953a3`. Candidate
`tomg-group-umd/CSD-ViT-L` at revision
`5bc26a6fb0487f3f00a2a7313135103a005b1b67`, tower `ViT-L-14-quickgelu`. The
incumbents are not pinned by this repository; the model cache on the machine
that produced these numbers held `openai/clip-vit-large-patch14` at `32bd6428`
and `facebook/dinov2-large` at `47b73eef`, which is a diagnostic rather than a
statement about which weights answered. Run with the `TORCH_NUM_THREADS=4 nice -n 19` prefix above, which
took about seventeen minutes; the thread count changes the order a reduction is
summed in and so the last digit, never the ranking.

| model | prefers the look | same look, diff. picture | same picture, diff. look | ratio |
|---|---|---|---|---|
| `csd-vit-l` (candidate) | **0.282** | 0.407 | 0.562 | 0.724 |
| `clip-vit-l14` | 0.033 | 0.570 | 0.830 | 0.686 |
| `dinov2-large` | 0.012 | 0.055 | 0.739 | 0.074 |

The bound is `(1 + 0.033) / 2 = 0.516`. The candidate reaches 0.282, so **no
third key was added** ([ADR-006](../adr/ADR-006-style-as-a-third-key.md)).

Per look, with the anchors restricted to that look:

| look | `csd-vit-l` | `clip-vit-l14` | `dinov2-large` |
|---|---|---|---|
| plain | 0.031 | 0.006 | 0.003 |
| grayscale | 0.046 | 0.003 | 0.002 |
| posterised | 0.087 | 0.004 | 0.002 |
| edges | **0.898** | 0.135 | 0.058 |
| painterly | 0.361 | 0.043 | 0.004 |
| sepia | 0.267 | 0.004 | 0.002 |

### Reading it

**A style descriptor is not an expensive synonym.** The worry that started this
measurement was that a third key would return what `dinov2-large` already
returns. It would not: the candidate separates manner from subject about eight
and a half times better than the best key the service stores.

**It still does not prefer the look.** 0.5 is indifference, and 0.282 is well
below it — shown a photograph, the candidate more often ranks the same *subject*
above the same *manner*. A key is bought to answer "find me pictures that look
like this one", and on this corpus none of the three models answers that
question; one is merely much closer than the others. Eight times a number close
to zero is still close to zero, which is why the bound is about the distance
left to a perfect score rather than a multiple of the incumbent. A "three times the
incumbent" rule would have set the bar at 0.099 and admitted the candidate, and
that is published here so a reader can disagree with the bound instead of with
the arithmetic.

**Most of the advantage is one filter.** `edges` throws away colour and texture
entirely and the candidate is nearly perfect on it (0.898). `plain` — the
untouched photograph, which is what a real style search would run against — is
0.031, the same order as the models it is supposed to beat. The average reads stronger than what stands behind it, and this is why
the breakdown is published beside it rather than underneath.

**The ratio is wrong on this table in both directions**, which is the clearest
argument for the number that decides. It puts `clip-vit-l14` at 0.686 against
the candidate's 0.724 — five per cent apart — where the ranking says 0.033
against 0.282. And it puts `clip-vit-l14` at nine times `dinov2-large` where the
ranking says three. CLIP's similarities sit in a narrow high band, which lifts both of
its means together and says nothing about the order results come back in.

**What this does not say.** Nothing about artistic style: the looks are filters,
not painters, and the `plain` row is the measure of how far they generalise.
Nothing about a corpus other than this one — a claim about somebody's own
pictures needs their own run of the same command. Nothing about a style model
other than this candidate. And nothing about whether a style vector is useful
for something that is not a ranking, which would be a different question with a
different bound.
