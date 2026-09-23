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

Gate 1 confirmation 2 of round 1: `/gate-review add-tag-and-meta-filters 1 confirm 1`.

Confirmation 1 confirmed the tier (finding 3) and rejected the arithmetic of
findings 1 and 2 — correctly, both times. Fixed: window reach
(`offset + limit + 1 + excluding`) and what the answer needs
(`offset + limit + 1`) are two named numbers rather than one confused one, and
the count that decides everything is taken over the candidates **before** the
offset and the threshold, so an empty page at a large offset no longer reads as
an exhausted ranking. Six worked rows in `design.md`, each a unit test in task
3.2.

**This is the second confirmation on findings 1 and 2.** If it fails again on
either, the process says to stop rather than loop: split the change or ask the
user to arbitrate.

## Blockers

None.
