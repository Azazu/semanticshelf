# Design — fix-dimension-constraint-name

## Context

See `proposal.md` — Why. Current state, read from the running database rather
than inferred: nine CHECK constraints carry doubled names (six on `assets`,
one on `embeddings`, two on `indexing_jobs`), while every primary key, foreign
key, unique constraint and index already matches the metadata exactly. The
cause is the interaction between the explicit names migration 0002 passes and
the `ck_%(table_name)s_%(constraint_name)s` convention in `app/db/base.py`:
for CHECK constraints a given name is substituted **into** the pattern rather
than used as-is, which is the one convention key that behaves that way.

Constraints on the approach: migration 0002 is applied in existing databases;
CI builds a database from scratch and runs the integration suite against it;
the marked integration suite is the only place that sees a real schema.

## Goals / Non-Goals

**Goals:** the deployed schema and the metadata agree on every constraint
name; the disagreement cannot come back unnoticed; the repair is reversible
and touches no data.

**Non-Goals:** see `proposal.md` — Non-goals. At design level, additionally:
no change to how names are chosen (the convention stays exactly as it is —
it is correct, and it was used incorrectly), and no attempt to make
autogenerate compare check constraints.

## Decisions

1. **A new revision renames; 0002 is left alone.** Editing an applied
   migration makes a fresh database and an existing one disagree about what
   that revision did, and it breaks the rule that history is append-only.
   Rejected alternative: fix the names in 0002 and add no revision — then
   every existing database keeps the doubled names forever and only new ones
   are correct, which is the worst of both.

2. **The revision writes the nine name pairs out explicitly.** A migration is
   frozen in time: it must keep saying what it said when it ran, so it does
   not import `Base.metadata` and does not compute names from the convention.
   This is the same rule change 3 applied when it wrote the model keys and
   dimensions into 0002 instead of importing them.

3. **The renames are unconditional.** Every database that exists came from
   0002, so every old name is present; a conditional rename would hide a
   database in a state nobody designed. If the upgrade fails because a name is
   missing, that is information, and the failure names the constraint.

4. **The guard is an integration test comparing the catalog with the
   metadata**, over every table the application owns and every constraint on
   it, as a set comparison — not "does this one name exist". It fails on an
   extra constraint and on a missing one, so it also covers a future migration
   that creates something the metadata does not declare.
   Rejected alternatives: a unit test grepping migration sources for
   already-prefixed names (it guards the one spelling of the mistake rather
   than the property, and says nothing about a database); a custom
   `include_object`/comparator in `env.py` teaching autogenerate about check
   constraints (a much larger change, and it would still only run when someone
   autogenerates).

5. **`downgrade()` renames back, and the existing migration round-trip test
   exercises it.** Change 3 already runs `upgrade head` → `downgrade base` →
   `upgrade head` on a throwaway database; this revision joins that path for
   free, which is why no new reversibility test is needed.

## Risks / Trade-offs

- [A database where someone renamed a constraint by hand] → the upgrade fails
  loudly, naming the constraint it could not find; no silent divergence, and
  the repair is a manual `ALTER TABLE … RENAME CONSTRAINT`.
- [The rename takes `ACCESS EXCLUSIVE` on each table] → it is a catalog update
  with no table rewrite, measured in milliseconds; on the databases this
  project has (development only, as `proposal.md` notes) it is not observable.
- [The guard compares names, not definitions] → it does not notice a
  constraint whose *expression* drifted from the metadata. That is a different
  property, and the storage tests in change 3 cover the behaviour those
  expressions enforce.
- [A future migration reintroduces the mistake] → the guard fails on the next
  integration run, which is also the run CI performs on every push.

## Migration Plan

1. `make migrate` (`alembic upgrade head`) applies the rename; no downtime
   consideration beyond the momentary lock, no data movement.
2. Verification: the new guard, plus `GET /ready` still answering 200 (it
   reads the dimension constraint by table, so it is name-independent and
   should be unaffected — worth checking precisely because it is the one
   caller that reads constraints at all).
3. Rollback: `alembic downgrade -1` restores the doubled names. Nothing else
   in the system holds the names, so rollback is complete.
