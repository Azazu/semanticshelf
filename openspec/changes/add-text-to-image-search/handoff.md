# Handoff — add-text-to-image-search

**Updated:** 2026-09-22 · claude
**State:** fixing-g2
**Branch:** change/add-text-to-image-search

## Done this session

Task groups 1-6 complete; 28 of 30 tasks checked.

- `EmbeddingRepository.nearest` takes a page and a maximum distance, as two
  selects: the inner one ordered by distance alone (the shape the index
  answers), the outer one breaking ties by identifier and dropping results
  beyond the distance.
- `app/services/search.py`: the query embedded on the inference pool, one
  transaction per search with `hnsw.ef_search` set inside it, one row beyond
  the page for `has_more`, three bounded queries per search.
- `app/api/search.py` and `app/api/catalogue.py`: `GET /search/text`,
  `GET /tags`, `GET /stats`; `app/api/deps.py` now holds the providers the
  routers share.
- `docs/how-to/searching.md`, written from a live service on the real weights.

Three things the work corrected, each in the commit body that carries it:

- the tie-break as a second `ORDER BY` key cost the index scan (the
  plan-reading test caught it);
- the design's claim that a threshold must not affect `has_more` was false, and
  its being false is what makes the row-beyond-the-page exact;
- the api suite could load real weights, which in CI is a 1.6 GB download —
  `tests/api/conftest.py` now keeps the whole suite on the fake.

## Next step

Gate 2 round 1 found one `major`, and it was right: the page was cut before the
order was total, so the index chose which equally distant rows it held. Fixed
on `90eb37b` — three layers now, with the page cut from the window once the
order is total.

What could not be fixed for free is which equally distant rows reach the window
at all; the alternative was measured (0.2 ms against 18.3 ms per search on
10 000 vectors) and the user chose the cheap mechanism with an honest
specification. The spec, the design and the how-to now say that a page is
ordered and repeatable while a group of identical scores spanning pages may be
divided arbitrarily.

Confirmation of round 1: `/gate-review add-text-to-image-search 2 confirm 1`.

Local evidence: `env -u DATABASE_URL make check` green (307 tests);
`make test-integration` green (183 tests).

## Blockers

None.
