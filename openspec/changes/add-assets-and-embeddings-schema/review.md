# Review — add-assets-and-embeddings-schema

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-20
**Reviewed-Commit:** b5856c3f4f2d29b898774ef24058a14e563a8d92
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | blocker | `tests/integration/test_migration_roundtrip.py:28,83-109` | The fixture unconditionally executes `DROP DATABASE IF EXISTS semanticshelf_roundtrip WITH (FORCE)` before creating its database. Because the name is fixed and there is no proof that this invocation created the existing database, a test run can destroy an unrelated database with that name; concurrent runs can also forcibly drop each other's active database. Generate a unique database name per invocation, create it without a pre-emptive drop, and clean up only that invocation's database. | open |
| 2 | minor | `tests/integration/test_asset_storage.py:48-57,119-127` | The index-plan test does not inspect the statement executed by `AssetRepository.find`; it reconstructs a reduced query in the test. The repository query can therefore regress to a non-indexable predicate while its functional assertions and this independent plan assertion both stay green. Expose/build the repository statement once and run `EXPLAIN` on that exact statement, as the embedding repository test already does. | open |
