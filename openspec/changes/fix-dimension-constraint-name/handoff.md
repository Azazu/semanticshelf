# Handoff — fix-dimension-constraint-name

**Updated:** 2026-09-21 · claude
**State:** implementing
**Branch:** change/fix-dimension-constraint-name

## Done this session

- Revision `0003_constraint_names` renames the nine doubled check constraints
  to the names the metadata declares, and renames them back on downgrade.
- `tests/integration/test_schema_names.py` compares the catalog's constraint
  names with the metadata's, per table, as sets — the guard that would have
  caught this in change 3.
- The dimension assertions in `tests/integration/test_embedding_storage.py`
  now match the name as PostgreSQL quotes it: they were green only because the
  doubled name contained the declared one.
- Roadmap row 4a corrected (autogenerate does not compare check constraints;
  nine constraints, not one). ADR-001 left untouched and now true again.

Evidence: `env -u DATABASE_URL make check` 124 passed; `make test-integration`
26 passed at head; the guard and both dimension assertions fail with the
revision downgraded; `openspec validate --all --strict` 6 passed; both script
suites and `sh -n` over every script clean; no agent trailer on the branch.

## Next step

The user pushes `change/fix-dimension-constraint-name` and reports the CI run
(task 5.3). On green: tick 5.3 and 5.4 and run
`/gate-review fix-dimension-constraint-name 2`.

## Blockers

None.
