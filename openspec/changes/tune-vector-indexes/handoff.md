# Handoff — tune-vector-indexes

**Updated:** 2026-09-26 · claude
**State:** awaiting-gate-2
**Branch:** change/tune-vector-indexes

(`implementing` is what a Gate 1 confirmation usually implies; here the
implementation was already done when the tier rose, so the open gate is the
second one.)

## Done this session
- **Gate 1 · round 1 — confirmed** at confirmation 2. Three majors:
  1. the removal table enumerated eight checks of thirteen — the five missing
     ones are demonstrated the same way (§8.6 of `tasks.md`), and
     `shipped_for()` gained the tests the table needed in order to break it;
  2. "nineteen of every twenty" read as a per-query guarantee, which over ten
     neighbours means all ten every time; the bound is on the **mean over at
     least fifty queries**, the worst single query is published rather than
     bounded, and the spec delta, its scenario, design decision 3, ADR-002,
     `benchmarks.md` and the CI guard now all say that;
  3. the claim that a real embedding corpus is easier than this one is gone
     from decision 1, the how-to and `scripts/index_benchmark.py`'s constants —
     nothing here compares the two, so no direction is claimed.
- **Gate 2 · round 1** was `changes-requested` before that (tier raised to
  `high`; the recall bound now covers every model). Both findings `fixed`.

## Next step
Push `change/tune-vector-indexes`, watch CI, and on green run
`/gate-review tune-vector-indexes 2 confirm 1` — the Gate 2 confirmation reviews
the diff since its round 1 (`2c90c91`), which is everything both gates asked
for.

## Blockers
None. Locally green: `make check` (635), `make test-integration` (293),
`openspec validate tune-vector-indexes --strict`, `scripts/pregate-verify.sh
gate1 tune-vector-indexes`.
