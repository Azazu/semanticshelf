# Design — add-assets-and-embeddings-schema

## Context

See `proposal.md` — Why. Current state: an application skeleton with settings, an async engine, an Alembic baseline that creates the `vector` extension, and no domain table. Constraints: the data model of the specification §3 is normative; repositories return domain objects (`AGENTS.md`); `make check` must stay green without a database, so everything touching PostgreSQL is an integration test; the executor has no `.env` and used a throwaway pgvector container on host port 5434 for every measurement below (PostgreSQL 16.14, pgvector 0.8.5).

## Goals / Non-Goals

**Goals:** the three tables with the constraints that make later changes safe; one storage layout for per-model vectors, chosen against measured alternatives and recorded in ADR-001; repositories that return domain objects and own the only query that reaches the vector index; a reversibility check that fails when a `downgrade()` forgets something.

**Non-Goals:** anything under Non-goals in the proposal; index tuning; query performance beyond "the index is used"; the job protocol.

## Measurements behind decision 1

Built on the throwaway container on 2026-09-20, 5000 rows per model, synthetic vectors, `EXPLAIN (ANALYZE)` after `ANALYZE`.

| Layout | Index built | Size, 5000 × 768 | Plan for a nearest-neighbour query |
|---|---|---|---|
| **A** one table, untyped `vector`, per-model CHECK, partial index on the cast expression | `USING hnsw ((vector::vector(768)) vector_cosine_ops) WHERE model = 'clip-vit-l14'` | 20 MB (768-d), 39 MB (1024-d) | `Index Scan using ix_emb_a_clip`, `Order By: ((vector)::vector(768) <=> …)` |
| **B** one table per model, typed `vector(768)` column | `USING hnsw (vector vector_cosine_ops)` | 20 MB | `Index Scan using ix_emb_b_clip` |
| **C** one table partitioned `BY LIST (model)`, index per partition on the cast | as A, without the `WHERE` | not measured; same index shape as A | `Index Scan using ix_emb_c_clip on emb_c_clip` with `Filter: (model = …)`, pruned to one partition |

Three further facts came out of the same session and shape the decisions below:

- A CHECK over `vector_dims(vector)` is accepted at DDL time and rejects both a wrong dimension and an unknown model key, because the constraint is a disjunction over the known keys. Both rejections were demonstrated.
- **The cast is load-bearing.** The identical query without `::vector(768)` in `ORDER BY` plans as `Seq Scan` + `Sort`: the index expression no longer matches. This is the one trap of layout A.
- A tag-filtered join (`embeddings ⋈ assets WHERE tags @> …`) planned as `Hash Join` + `Seq Scan` + `Sort` at this corpus size: the vector index was not used at all. Filtered vector search is `add-tag-and-meta-filters` (change 12); the plan is recorded there as the starting point, not solved here.

A second probe answered the integration question in an ephemeral environment: with SQLAlchemy 2.0.54, asyncpg and `pgvector`, an untyped `Vector()` column inserts and reads back a `list[float]` with no codec registration and no connection hook, and `sa.cast(Embedding.vector, Vector(768)).cosine_distance(q)` compiles to `CAST(embeddings.vector AS VECTOR(768)) <=> $1` and reaches the index.

## Decisions

1. **One `embeddings` table, untyped `vector` column, one partial expression index per model key (layout A).** The index costs the same as a typed column, the table stays one table, and adding a model is a migration that extends the CHECK and adds an index — no new table, no repository branch, no `UNION` for cross-model reads such as index status or statistics. Layout B was rejected because every cross-model read and every new model would touch code, not only schema. Layout C was rejected as capability we cannot yet justify: partitioning buys physical separation and per-partition maintenance that a corpus of this size does not need, and it still needs the same cast; the FK from a partitioned table with `ON DELETE CASCADE` was verified to work, so C stays a viable migration target if `tune-vector-indexes` finds a reason. ADR-001 records this with the table above.
2. **The cast lives in exactly one place.** Only `EmbeddingRepository.nearest()` builds a vector query, and it always casts. An integration test reads the execution plan and fails when the plan is not an index scan, so a future edit that drops the cast is caught by a test rather than by a slow production query. This is the mitigation that makes decision 1 safe.
3. **One CHECK carries both the dimension and the model allowlist.** `(model = 'clip-vit-l14' AND vector_dims(vector) = 768) OR (model = 'dinov2-large' AND vector_dims(vector) = 1024)`. An unknown key satisfies no branch and is rejected, so the specification's "CHECK against the known keys" needs no second constraint.
4. **Model keys and dimensions are declared twice on purpose.** `app/domain.py` holds `EMBEDDING_MODELS`, the authority the application reads. The migration hardcodes its own copy, because a migration is a historical record and must not follow a constant that changes after it ran. A unit test asserts that the application's declaration matches the constraint the current head migration installed, so extending one without the other fails `make check`. Alternative rejected: importing the constant into the migration, which makes old revisions change meaning.
5. **Repositories return frozen dataclasses.** `app/domain.py` declares `Asset`, `Embedding`, `IndexingJob` and `NeighbourHit`; `app/repositories/` maps ORM rows to them and never returns an ORM instance, so a session that closed cannot turn a field access into a query. Pydantic schemas stay at the HTTP edge (change 5). `app/domain.py` is a module rather than a package while it holds four dataclasses and one mapping; it becomes a package when it grows.
6. **The surrogate `id` on `embeddings` is kept**, as the specification fixes it, although `(asset_id, model)` is the natural key and nothing references an embedding by id. The cost is one uuid and one index per row; the benefit is a uniform shape across the three tables and a stable handle if an embedding ever becomes addressable. Revisiting it would be a specification amendment for a marginal gain.
7. **HNSW build parameters are written out, not inherited silently.** The migration states `m = 16, ef_construction = 64` — pgvector's defaults — so the values are visible where they are used and a change is a reviewed diff. Choosing better values needs recall and latency numbers, which belong to ADR-002.
8. **The vector indexes are created by the migration and also declared in the ORM metadata** as expression indexes, so a later `alembic revision --autogenerate` does not propose dropping them. Alembic does not compare expression-based indexes, which is exactly the behaviour wanted here: declared for documentation, not diffed. A task verifies this by generating a probe revision against the migrated database and confirming it is empty.
9. **Reversibility is an integration test on a throwaway database**, not a separate CI job. The test creates a database of its own, migrates to head, fingerprints the schema from the catalog (tables, columns, types, nullability, defaults, constraints, index definitions, sorted), migrates down to base and up again, fingerprints once more, compares, and drops the database. This satisfies NFR-REL-3 with no new command, no `pg_dump` dependency and no CI edit, and it runs everywhere the integration suite runs. The specification's wording is amended to match. What it does not prove: that a downgrade preserves data, which no downgrade in this project claims.
10. **The jobs table arrives without its protocol.** `IndexingJobRepository` can add a job for an asset and a model and list an asset's jobs; it cannot claim, lease or finish one. Claiming with `FOR UPDATE SKIP LOCKED`, leases, backoff and the uniqueness question ("one live job per asset and model" or a history of attempts) are decided in `add-background-indexing`, which owns the behaviour and the ADR.
11. **Alembic sees the models through `app/models/__init__.py`.** `alembic/env.py` imports that package so `Base.metadata` is populated for autogenerate; the ORM modules import nothing from `alembic`, keeping the dependency one-way.

## Risks / Trade-offs

- [A query written without the cast silently falls back to a sequential scan] → decision 2: one repository method, one plan-asserting integration test.
- [The application's model declaration and the migration's copy drift apart] → decision 4: a unit test compares the application's declaration with the constraint installed in the database; it fails on the first divergence.
- [Autogenerate proposes dropping the hand-written vector indexes] → decision 8 plus the probe-revision task; if Alembic does compare them after all, the fallback is an `include_object` filter in `env.py`, and the task records which of the two was needed.
- [The round-trip test needs the privilege to create a database] → the Compose database and the CI service both run as an owner role that has it; the test skips with a clear message when the privilege or `DATABASE_URL` is missing, exactly as the readiness integration test already does.
- [Filtered vector search is unsolved] → measured and recorded, owned by change 12; nothing in this change promises it.

## Migration Plan

Apply on the branch; `make check` green without a database; `make migrate` and `make test-integration` green against a pgvector database; user pushes; CI green; Gate 2; merge. Rollback: revert the merge commit, then `alembic downgrade 0001_baseline`, which drops the three tables and their indexes.

## Open Questions

None.
