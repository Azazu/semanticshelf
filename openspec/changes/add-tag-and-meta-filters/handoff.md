# Handoff — add-tag-and-meta-filters

**Updated:** 2026-09-23 · claude
**State:** implementing
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

`/opsx:apply add-tag-and-meta-filters` — Gate 1 passed (Confirmation 2 of round
1, all four findings confirmed or fixed). The order of `tasks.md` is the order
to take: what a narrowing *is* before anything applies one.

Three things the implementation must not soften, because each is a finding that
was paid for twice:

- the scan's report is decided by `reached` against `needed`, never by the shape
  of the answer;
- `reached` is counted after the exclusion and **before** the offset and the
  threshold — an empty page is not evidence of anything;
- the window asks for one row more than the answer needs when an asset excludes
  itself, and that row is the window's, not the page's.

## Blockers

None.
