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

Gate 1 round 2: `/gate-review add-tag-and-meta-filters 1`. Round 1 confirmed a
design whose central evidence turned out to be conditional, and the artifacts
now say what was measured instead.

What changed since that confirmation:

- **The Context's evidence is two measurements, not one.** The first, on a table
  that had never been `ANALYZE`d, is the empty page FR-FLT-2 forbids. The second,
  after `ANALYZE`, is a full page at every selectivity from 1 in 2 to 1 in 100 —
  because PostgreSQL leaves the vector index as soon as a narrowing is selective
  and answers exactly over the narrowed rows. The first measurement was mine,
  and generalising from it was my error, not the reviewer's.
- **Decision 2 keeps the iterative scan for the reason that survives**: it is
  what fills a page on the path where the index *is* used, which is broad
  narrowings, stale statistics, and corpora where the exact plan stops being
  cheap.
- **Decision 7 is now half the point of the change**: the benchmark measures
  which plan answers at each selectivity, with and without statistics, and what
  each costs. That is the number change 14 needs and cannot get elsewhere.
- **Task 3.5 no longer asks for an integration test of the scan's bound.** On
  this corpus such a test can only fire by defeating the planner's statistics,
  and would test the fixture. The rule stays in the unit tests of task 3.2, and
  what the bound costs is the benchmark's question.

Implementation state: 8 of 26 tasks done and committed (the narrowing value and
its parser, the predicate inside the window, the iterative scan, the cut and the
decision function with their unit tests). `make check` 511, integration 236, all
green. Groups 4 to 7 are untouched and do not depend on this review.

## Blockers

None — the question that blocked the apply was answered by the user: rewrite the
justification around the measurement and ask Gate 1 again.
