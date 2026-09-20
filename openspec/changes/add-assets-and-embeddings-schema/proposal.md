# Proposal — add-assets-and-embeddings-schema

**Risk-Tier:** medium

Tier rationale: an ordinary schema change plus the repositories over it. No HTTP surface, no upload or deletion endpoint, no concurrency protocol, no model download. The reversibility check arrives as an integration test on a throwaway database rather than as a new CI job, so `.github/workflows/ci.yml` and the verifier scripts are untouched and the `high` trigger for CI infrastructure does not fire.

## Why

The application has a baseline migration that creates the pgvector extension and nothing else. Every change from here on needs the domain tables: upload writes assets, extraction writes embeddings, indexing writes jobs, search reads vectors. The storage decisions those changes depend on — how a model's vectors are kept apart, where the dimension is enforced, which index answers a nearest-neighbour query — are exactly the ones that are expensive to revise later, so they are made once here, measured, and recorded in ADR-001.

## What Changes

1. **Dependency.** The `pgvector` Python package: the SQLAlchemy `Vector` column type and its value binding. Measured in an ephemeral environment on 2026-09-20: with SQLAlchemy 2.0.54 and asyncpg the type binds and parses through its own processors, so no asyncpg codec registration and no connection hook are needed.
2. **Three tables and one migration** (`0002_asset_schema`, reversible, on top of `0001_baseline`): `assets`, `embeddings`, `indexing_jobs` exactly as the specification fixes them in §3, with their CHECK constraints, GIN indexes for tags and metadata, and the listing and claim indexes.
3. **Per-model vector storage.** One `embeddings` table with an untyped `vector` column, a single CHECK that enumerates the known model keys with their dimensions, and one partial HNSW cosine index per key over the dimension-cast expression. The alternatives (a table per model, LIST partitioning by model) were built and measured on PostgreSQL 16.14 with pgvector 0.8.5; ADR-001 records the plans, the sizes and the trade-offs.
4. **Model registry constant.** `app/domain.py` holds the model keys and their dimensions as the application's authority. The migration carries its own frozen copy, because a migration must not follow a constant that later changes; a unit test asserts the two agree, so extending one without the other fails.
5. **Domain objects and repositories.** Frozen dataclasses for `Asset`, `Embedding`, `IndexingJob` and a nearest-neighbour hit; `app/repositories/` returns them and never leaks ORM instances. The embedding repository owns the only query that reaches the vector index, including the cast the index needs.
6. **Reversibility check.** `tests/integration/test_migration_roundtrip.py` creates a throwaway database, migrates to head, fingerprints the schema from the catalog, migrates down to base and up again, fingerprints once more and compares. A downgrade that forgets something fails it.
7. **ADR-001** records the storage-layout decision with the measured evidence, and states what it does not decide (HNSW versus IVFFlat, build parameters, filtered-query behaviour — all ADR-002 in `tune-vector-indexes`).
8. **Documentation.** `AGENTS.md` layout gains `domain.py` and `repositories/`; `docs/reference/commands.md` gains nothing new, because the check needs no new command; the specification's NFR-REL-3 is amended to name the integration test instead of a separate CI job.

## Capabilities

### New Capabilities

- `asset-storage`: what an asset record guarantees — content uniqueness, the field domains the database enforces, queryable tags and metadata, and the removal of everything derived from an asset.
- `embedding-storage`: what an embedding guarantees — one per asset and model, a dimension fixed per model and enforced by the database, and an index-backed nearest-neighbour lookup that never mixes models.

### Modified Capabilities

None.

## Non-goals

- No HTTP endpoint: assets, uploads, files, listings and search arrive in changes 5, 8 and 11. Nothing in this change is reachable over the network.
- No job protocol: claiming, leases, retries, backoff and the `SKIP LOCKED` query are `add-background-indexing` (change 6) and `add-indexing-worker` (change 13). This change creates the table, a plain enqueue and a read per asset; the repository does not claim or finish a job.
- No embedder, no model download, no real vectors: tests use deterministic synthetic vectors. The `Embedder` protocol is change 4.
- No index tuning: HNSW build parameters stay at pgvector's defaults, stated explicitly in the migration; HNSW versus IVFFlat, recall and latency belong to ADR-002 (change 14). This change proves the index is used, not that it is the best index.
- No filtered-vector-query strategy: the measured plan for a tag-filtered join is recorded in ADR-001 as a starting point for `add-tag-and-meta-filters` (change 12), which owns the decision.
- No edit to `.github/workflows/ci.yml` or to the verifier scripts. If a CI run proves an edit necessary, this change stops with a `blocked` handoff and the edit is designed, tasked and reviewed before it is made.
- No `alembic check` / autogenerate drift gate: the round trip proves reversibility, not metadata parity. A task verifies that autogenerate does not propose dropping the hand-written vector indexes; a drift gate may come later.

## Impact

- New: `app/domain.py`, `app/models/{__init__,asset,embedding,indexing_job}.py`, `app/repositories/{__init__,assets,embeddings,jobs}.py`, `alembic/versions/0002_asset_schema.py`, `docs/adr/ADR-001-per-model-vector-index-layout.md`, `tests/unit/test_domain.py`, `tests/integration/{test_asset_storage,test_embedding_storage,test_migration_roundtrip}.py`.
- Modified: `pyproject.toml` and `uv.lock` (the `pgvector` dependency), `app/db/base.py` (metadata unchanged, models imported for Alembic), `alembic/env.py` (import the models so `target_metadata` is populated), `AGENTS.md` (layout, and the domain-rule line about the job table), `docs/explanation/requirements.md` (NFR-REL-3 wording; §3 unchanged), `docs/adr/README.md` (ADR index).
- One new runtime dependency, `pgvector`, justified against the anti-overengineering rule: the `vector` column type and its binding for SQLAlchemy; the specification names it in §5 and nothing already present can express the type.
- No new setting, so the environment template is untouched.
