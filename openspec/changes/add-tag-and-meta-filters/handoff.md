# Handoff — add-tag-and-meta-filters

**Updated:** 2026-09-23 · claude
**State:** awaiting-gate-1
**Branch:** change/add-tag-and-meta-filters
**Security-sensitive:** yes — this change handles client input: a shared
parser for tag and metadata narrowings on four public surfaces, including the
multipart picture search, with parameters whose names the caller invents.
§Security-Sensitive Code of `AGENTS.md` puts that at `high`, which is why the
tier was raised at Gate 1 round 1.

## Done this session

Branch, scaffold and all four planning artifacts. The central question — how a
filter and an approximate index scan are made to agree — was settled by
measurement rather than by reading, and the table is in `design.md`: on 3 000
assets with one in three hundred carrying the tag, a page of 20 came back with
**0 rows** at `hnsw.iterative_scan = off` (the index produced its 40 candidates,
none of them matched) and with **10 rows** — every match that exists — at
`strict_order`. That is FR-FLT-2's requirement failing and passing in front of
you, and it decides decision 2.

`relaxed_order` returned the same ten here and is still rejected: it may return
rows slightly out of order, and this statement cuts the window by distance
before the page re-orders, so a late arrival can be cut although it belonged
inside.

Also settled: the scan's own bound is part of the contract, so a narrowed page
that comes back short asks one bounded question — do more matches exist than
this answer holds? — and the envelope says whether the search stopped early.
Without it a short page cannot be told from the end of a ranking.

**A note on the local store:** the measurement ran against the database this
machine uses for both development and the integration suite, and it truncated
the tables. The demo corpus was rebuilt afterwards (`storage prune --apply`,
then `DEMO_COUNT=20 make demo`): 20 assets, 40 vectors, both models `done`.

## Next step

Gate 1 confirmation of round 2: `/gate-review add-tag-and-meta-filters 1 confirm 2`.
All three findings are `fixed`, and each was a place where the rewrite had not
been carried all the way through:

1. The delta spec still demanded the vector index for every narrowed search —
   forbidding the exact plan the same rewrite had just accepted. It now requires
   what actually matters (no narrowed search reads every stored vector, and the
   answer does not depend on which plan ran) and keeps a targeted requirement
   that the index path works when it is chosen.
2. Removing the database-backed positive case left `scan_limited` with no test
   that could catch a mis-wiring: the unit tests feed the arithmetic its own
   inputs. Task 3.5 now asks for the positive path end to end, and it can be
   built without touching the planner's statistics — measured: a narrowing over
   half the corpus keeps the vector index *with* statistics, and a lowered scan
   budget then leaves the page one row short of what it needed while fifteen
   hundred matches remain.
3. The benchmark was planned to empty the tables `DATABASE_URL` names. It now
   builds in a schema it creates and drops, a test asserts the documented
   command leaves a populated store untouched, and the applicability table stops
   claiming that nothing here deletes — on this machine that mistake already
   cost the demo corpus once.

## Blockers

None.
