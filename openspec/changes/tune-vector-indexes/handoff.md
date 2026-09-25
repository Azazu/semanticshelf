# Handoff — tune-vector-indexes

**Updated:** 2026-09-25 · claude
**State:** fixing-g2
**Branch:** change/tune-vector-indexes

## Done this session
- Gate 2 round 1 came back `changes-requested` with two findings; both are now
  `fixed` in `review.md`.
- **Finding 1 (major), accepted: the tier is `high`, not `medium`.** The
  `--schema` value is checked and then interpolated into `CREATE SCHEMA`, table
  DDL and `DROP SCHEMA ... CASCADE` — security-sensitive input handling and
  deletion, both `high` triggers, and change 12 was raised for the same reason.
  What `high` asks for is now there: the applicability table in `design.md`
  (deletion, input, crash around the external effect, concurrent writers,
  idempotent retries, empty inputs, with what each does **not** guarantee), the
  two inline checks of `sweep` named as functions so they can be exercised, an
  `--assets` floor, the shared guard's own unit and integration tests — including
  the one that matters most: `guard()` refuses when an unqualified name resolves
  to the service's own table — and a demonstrated failing input for every new or
  changed check (§8.6 of `tasks.md`: eight removals, eight failures).
- **Finding 2 (minor), fixed:** the recall bound is asserted for every model in
  `EMBEDDING_MODELS`, not only `clip-vit-l14`.
- Tier reconciled in `openspec/ROADMAP.md` row 14 and `docs/explanation/requirements.md`
  §7 row 14.

## Next step
`high` requires Gate 1 on the artifacts, which this change never had:
`/gate-review tune-vector-indexes 1`. On its approval, Gate 2 confirmation of
round 1 (`/gate-review tune-vector-indexes 2 confirm 1`).

## Blockers
None. Locally green: `make check` (633), `make test-integration` (293),
`openspec validate tune-vector-indexes --strict`.
