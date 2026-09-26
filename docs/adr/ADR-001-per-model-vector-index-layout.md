# ADR-001: One embeddings table, one partial expression index per model

**Date:** 2026-09-20
**Status:** accepted
**Related:** [ADR-002](ADR-002-vector-index-family-and-parameters.md) (index family and build parameters, written by `tune-vector-indexes`: HNSW stays, at these parameters, measured); authored by the OpenSpec change `add-assets-and-embeddings-schema`

## Context

Every vector in this service belongs to a model, and vectors of different models are never comparable: CLIP's 768-wide joint text-image space and DINOv2's 1024-wide feature space describe different things, and a nearest-neighbour query that mixed them would return nonsense with a plausible score. The schema has to make that mixing impossible, keep each model's vectors reachable through an index, and stay cheap to extend when a third model arrives.

pgvector indexes a column only when its width is fixed, so the shape of the table and the shape of the index are one decision, not two. Three layouts were built and measured on the same machine before choosing, on PostgreSQL 16.14 with pgvector 0.8.5, 5000 rows per model, `EXPLAIN (ANALYZE)` after `ANALYZE`:

| Layout | Index | Size, 5000 × 768 | Plan of a nearest-neighbour query |
|---|---|---|---|
| **A** one table, untyped `vector` column, per-model CHECK, partial index on the cast expression | `USING hnsw ((vector::vector(768)) vector_cosine_ops) WHERE model = 'clip-vit-l14'` | 20 MB (768), 39 MB (1024) | `Index Scan using ix_emb_a_clip`, `Order By: ((vector)::vector(768) <=> …)` |
| **B** one table per model, typed `vector(768)` column | `USING hnsw (vector vector_cosine_ops)` | 20 MB | `Index Scan using ix_emb_b_clip` |
| **C** one table partitioned `BY LIST (model)`, index per partition on the cast | as A without the `WHERE` | same shape as A | `Index Scan using ix_emb_c_clip on emb_c_clip`, pruned to one partition |

Three further measurements from the same session:

- A CHECK over `vector_dims(vector)` is accepted at DDL time and rejects a wrong width **and** an unknown model key, because the constraint is a disjunction over the known keys. Both rejections were demonstrated.
- The same query **without** the cast in `ORDER BY` plans as `Seq Scan` + `Sort`. The index expression no longer matches, and nothing warns.
- A tag-filtered join (`embeddings ⋈ assets WHERE tags @> …`) planned as `Hash Join` + `Seq Scan` + `Sort` at this corpus size: the vector index was not used at all.

A separate probe confirmed the layout is reachable from the application stack: with SQLAlchemy 2.0.54, asyncpg and `pgvector` 0.5.0, an untyped `Vector()` column inserts and reads back a `list[float]` without registering a codec, and `cast(Embedding.vector, Vector(768)).cosine_distance(q)` compiles to `CAST(embeddings.vector AS VECTOR(768)) <=> $1` and reaches the index.

## Decision

**Layout A.** One `embeddings` table holds every model. Its `vector` column is declared without a width. One CHECK constraint, `ck_embeddings_model_dimension`, enumerates the known model keys with their widths and therefore enforces both the allowlist and the width. Each key gets one partial HNSW cosine index over `(vector::vector(<width>))` restricted to that key, built with `m = 16` and `ef_construction = 64` stated explicitly in the migration.

Adding a model is one migration: extend the CHECK and add an index. No new table, no repository branch, no `UNION` for a cross-model read.

Because the index is on an expression, **every vector query must carry the same cast**. That is contained by construction: `EmbeddingRepository.nearest()` is the only place in the service that builds a vector query, and an integration test reads the execution plan of exactly the statement it builds and fails when the plan is not an index scan on that model's index. Removing the cast was demonstrated to turn the plan into `Limit → Sort` and to fail that test.

The application declares the same keys and widths in `app/domain.py`; the migration carries its own frozen copy, and a unit test compares the two, including the generated CHECK text.

**What this does not decide:** whether HNSW is the right index family, whether 16 and 64 are the right build parameters, what recall the defaults give, and how a filtered vector query should be planned. Those need measured recall and latency on a real corpus and belong to ADR-002 (`tune-vector-indexes`) and to `add-tag-and-meta-filters`.

## Alternatives considered

**B — one table per model.** Same index size, and the query needs no cast, which removes the one trap of layout A. It lost on everything that is not a nearest-neighbour query: a cross-model read (an asset's index status, the statistics endpoint, a deletion cascade check) becomes a `UNION` over a set of tables that grows with the registry, and adding a model becomes a code change rather than a migration. The trap it avoids is already contained by a single repository method and a plan-asserting test.

**C — partitioning by `LIST (model)`.** Works, prunes to one partition, and a foreign key from the partitioned table to `assets` with `ON DELETE CASCADE` was verified to behave (the first probe suggested otherwise; that turned out to be an artifact of synthetic data, and the corrected probe cascaded correctly). It lost as capability we cannot yet justify: the physical separation and per-partition maintenance buy nothing at this corpus size, the cast is still required, and every new model needs a `CREATE TABLE … PARTITION OF` plus a default-partition decision. It stays the natural migration target if `tune-vector-indexes` finds a reason to rebuild one model's index independently.

**A typed column per model in one table** (`vector_768`, `vector_1024`, …) was not measured: it turns every added model into a schema change of the same table, makes the row sparse, and needs a CHECK to keep exactly one column non-null. It combines the costs of A and B.

## Consequences

- Adding a model key costs one reviewed migration and no application branching.
- Model isolation is a property of the schema and the query predicate, not of caller discipline: a lookup filters on the model key, so another model's row cannot be ranked into a result.
- The cast is a real trap, now guarded by a test rather than by memory; a reader of `EmbeddingRepository` finds the reason at the call site.
- Storage and index size are the same as the typed-column layout, so nothing is paid for the flexibility.
- The `alembic check` and autogenerate path prints a notice that it cannot compare the expression indexes, and skips them. That is why they are declared in the ORM metadata under the same names: declared, so autogenerate never proposes dropping them; not compared, so a probe revision comes out empty. Moving the operator class into `postgresql_ops` silences the notice but drops the class from the emitted DDL, which would make the declaration describe an index that could not be built; rejected.
- Filtered vector search is left unsolved and measured, not hidden: at 5000 rows a tag-filtered join did not use the vector index at all.

## Supersedes

No ADR clause.
