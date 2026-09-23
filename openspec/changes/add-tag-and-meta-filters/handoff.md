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

`/opsx:apply add-tag-and-meta-filters` — Gate 1 round 2 confirmed, all three
findings resolved. 8 of 28 tasks are done and committed; the rest, in order:

- **3.5 / 3.5a** the scan-limit evidence, positive and negative. The positive
  one needs no games with statistics: a narrowing over half the corpus keeps the
  vector index, and a lowered scan budget then leaves the page one candidate
  short while fifteen hundred matches remain.
- **3.6 / 3.7** the bounded question only when it is needed, and the envelope.
- **4.x** the four surfaces, `meta.<key>` read from the raw parameters.
- **5.x** the interface's tag box becomes the service's filter.
- **6.x** the benchmark, in a schema it creates and drops, and the numbers.
- **7.x** the documentation and the evidence.

What the review cost and bought, worth remembering at Gate 2: three rounds of
Gate 1 on this change, and every finding was a contradiction between what the
artifacts claimed and what the database does. The measurement that started it —
one probe without `ANALYZE` — is why the change now carries a benchmark rather
than a slogan.

## Blockers

None.
