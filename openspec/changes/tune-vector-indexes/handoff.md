# Handoff — tune-vector-indexes

**Updated:** 2026-09-25 · claude
**State:** fixing-g1
**Branch:** change/tune-vector-indexes

## Done this session
Gate 2 round 1 (two findings) and Gate 1 round 1 (three findings) are all
`fixed` in `review.md`.

Gate 1 round 1:
- **Finding 1** — the removal table enumerated eight checks; the change has
  thirteen. The five it missed are demonstrated the same way and added to §8.6:
  the protected-name branch of `unusable()`, the `--queries` bounds,
  `shipped_for()`'s refusal, and the empty-input guards of `recall_at()` and
  `percentile()`. `shipped_for` gained the two unit tests the table needed in
  order to have something to break.
- **Finding 2** — "at least nineteen of every twenty" read as a per-query
  guarantee, which over ten neighbours means all ten every time. The bound is on
  the **mean over at least fifty queries**, and the worst single query is
  published rather than bounded. Said the same way now in the spec delta, its
  scenario, design decision 3, ADR-002 and `benchmarks.md` — and the CI guard
  averages over fifty queries too, so it measures the statistic the requirement
  names.
- **Finding 3** — the design called the measured recall a floor for real
  embeddings on the grounds that a real corpus is easier. Nothing here compares
  the two, so the direction is not claimed at all; ADR-002 already said so, and
  the design now agrees.

## Next step
`/gate-review tune-vector-indexes 1 confirm 1`. On its confirmation, Gate 2
confirmation of round 1 (`/gate-review tune-vector-indexes 2 confirm 1`), which
needs a push and a green CI run on that HEAD first.

## Blockers
None. Locally green: `make check` (635), `make test-integration` (293),
`openspec validate tune-vector-indexes --strict`,
`scripts/pregate-verify.sh gate1 tune-vector-indexes`.
