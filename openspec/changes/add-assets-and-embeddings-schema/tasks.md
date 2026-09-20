## 1. Dependency and model registry

- [ ] 1.1 Add the `pgvector` runtime dependency with `uv add pgvector` and commit the lock. Verify: `make lock-check` exits 0 and `uv run python -c 'from pgvector.sqlalchemy import Vector; print(Vector().compile())'` prints `VECTOR`.
- [ ] 1.2 Write `app/domain.py` with the frozen dataclasses `Asset`, `Embedding`, `IndexingJob`, `NeighbourHit` and the mapping `EMBEDDING_MODELS` from model key to dimension (`clip-vit-l14` → 768, `dinov2-large` → 1024), plus the job status values. Verify: `tests/unit/test_domain.py` asserts the dataclasses are frozen, that every dimension is positive, and that the keys are the two the specification fixes.

## 2. Schema and migration

- [ ] 2.1 Write the ORM models under `app/models/` — `Asset`, `Embedding`, `IndexingJob` — with the columns, CHECK constraints and plain indexes of specification §3, the untyped `Vector()` column, and the two vector indexes declared as expression indexes (design decision 8). Verify: `uv run python -c 'from app.models import Asset, Embedding, IndexingJob; from app.db.base import Base; print(sorted(Base.metadata.tables))'` lists the three table names, and `make types` stays green.
- [ ] 2.2 Import `app/models/__init__.py` from `alembic/env.py` so `target_metadata` is populated. Verify: `uv run alembic check` against a migrated database reports no new operations, or the exact reason it cannot, recorded in the commit body.
- [ ] 2.3 Write `alembic/versions/0002_asset_schema.py`: the three tables, the single dimension-and-allowlist CHECK on `embeddings` (design decision 3) with its own frozen copy of the model keys and dimensions (decision 4), the GIN indexes for tags and metadata, the listing and claim indexes, and one partial HNSW cosine index per model key over the cast expression with `m = 16, ef_construction = 64` stated explicitly; `downgrade()` drops all of it and leaves `0001_baseline`. Verify: `make migrate` applies it against a pgvector database and `uv run alembic current` prints `0002_asset_schema (head)`, both recorded in the commit body.
- [ ] 2.4 Add the unit test that the application's `EMBEDDING_MODELS` and the migration's frozen copy agree (decision 4). Verify: the test fails when a key or a dimension is changed in only one of the two, demonstrated and recorded in the commit body.

## 3. Domain objects and repositories

- [ ] 3.1 Write `app/repositories/` with `AssetRepository` (add, get, get by content hash, delete), `EmbeddingRepository` (upsert, get, `nearest(model, vector, limit)`) and `IndexingJobRepository` (add for a model, list for an asset). Every method returns the frozen dataclasses of `app/domain.py` and never an ORM instance. `nearest()` is the only place that builds a vector query and always casts the column to the model's dimension (design decisions 1 and 2). Verify: `make types` green under `mypy --strict`, and a unit test asserts the repository module does not export any ORM class.
- [ ] 3.2 Update the `AGENTS.md` layout block with `domain.py` and `repositories/`. Verify: re-read the block whole; `rg -n 'repositories|domain' AGENTS.md` shows the layout and the domain-rule lines agreeing with the code.

## 4. Storage guarantees against a real database

- [ ] 4.1 Integration tests for `asset-storage`: a second record with the same content hash is rejected; an unsupported content type, an unsupported extension, an unsupported source and a non-positive width, height or size are each rejected; tag containment and metadata containment queries return exactly the matching assets; removing an asset removes its embeddings and jobs in the same transaction; an embedding or job written for an absent asset is rejected. Verify: `make test-integration` green, one test per scenario of the delta spec.
- [ ] 4.2 Integration tests for `embedding-storage`: writing the same asset and model twice leaves one row holding the last vector; two models for one asset coexist; a wrong dimension and an unknown model key are each rejected by the database; `nearest()` returns that model's assets ordered by ascending cosine distance; a second model's vectors never appear, including when both dimensions are made equal in the fixture. Verify: `make test-integration` green, one test per scenario.
- [ ] 4.3 Plan assertion: a test runs `EXPLAIN` on the statement `nearest()` builds and asserts the plan contains an index scan on that model's vector index and no sequential scan of `embeddings`. Verify: the test fails when the cast is removed from the repository query, demonstrated and recorded in the commit body.

## 5. Reversibility and autogenerate

- [ ] 5.1 Write `tests/integration/test_migration_roundtrip.py`: create a throwaway database, migrate to head, fingerprint the schema from the catalog (tables, columns, types, nullability, defaults, constraint definitions, index definitions, sorted), migrate down to base, migrate up again, fingerprint once more, compare, drop the database; skip with a clear message when `DATABASE_URL` is unset or the role may not create a database. Verify: `make test-integration` green.
- [ ] 5.2 Demonstrate the round trip catches a broken `downgrade()`: temporarily remove one index drop from `0002_asset_schema`, run the test, record the failure and its message, restore the file. Verify: the output recorded in the commit body and `git status --short` clean afterwards.
- [ ] 5.3 Autogenerate probe (design decision 8): against the migrated database run `make revision MSG='probe'`, confirm the generated revision proposes nothing — in particular no drop of the vector indexes — then delete the generated file. If it does propose a drop, add the `include_object` filter to `alembic/env.py` instead and say so. Verify: the generated file's operations and the outcome recorded in the commit body; `git status --short` clean afterwards.

## 6. ADR and documentation

- [ ] 6.1 Write `docs/adr/ADR-001-per-model-vector-index-layout.md`: the decision, the three measured layouts with their plans and sizes, the cast trap and its guard, what the ADR does not decide (HNSW versus IVFFlat, build parameters, filtered queries — ADR-002), and the conditions that would reopen it. Add the row to `docs/adr/README.md`. Verify: re-read both whole; every number in the ADR came from a command recorded in this change's commit bodies.
- [ ] 6.2 Amend `docs/explanation/requirements.md` NFR-REL-3 to name the integration test on a throwaway database instead of a separate CI job (design decision 9), leaving §3 unchanged. Verify: `rg -n 'NFR-REL-3' docs/` shows one statement and it matches what the test does.

## 7. Wrap-up

- [ ] 7.1 Commits per block, without agent trailers: `chore(deps): add pgvector`, `feat(domain): model registry and domain objects`, `feat(db): assets, embeddings and indexing jobs`, `feat(repositories): asset, embedding and job repositories`, `test(db): storage guarantees and migration round trip`, `docs(adr): record the per-model vector index layout`. Verify: `git log --format=%B main..HEAD | grep -c '^Co-Authored-By'` prints `0`.
- [ ] 7.2 `make check` green without a database (`env -u DATABASE_URL make check`) and `make migrate && make test-integration` green against a pgvector database. Verify: both outputs recorded in the commit bodies.
- [ ] 7.3 Acceptance on GitHub (user pushes the branch): `workflow` green and `python` green, the integration step now running the storage and round-trip tests against the service. Verify: the user reports the run.
- [ ] 7.4 `openspec validate add-assets-and-embeddings-schema --strict` and `scripts/pregate-verify.sh gate2 add-assets-and-embeddings-schema` pass; request Gate 2 with `/gate-review add-assets-and-embeddings-schema 2`.
