# Handoff — add-tag-and-meta-filters

**Updated:** 2026-09-23 · claude
**State:** proposing
**Branch:** change/add-tag-and-meta-filters

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

The tier is `medium`, so the process requires only Gate 2. **The executor asks
for Gate 1 anyway** — the risk of this change is in `design.md`, not in the
code that follows it, and the last change's Gate 1 found three real design
errors. If the user agrees: `/gate-review add-tag-and-meta-filters 1`.
Otherwise straight to `/opsx:apply add-tag-and-meta-filters`.

## Blockers

None.
