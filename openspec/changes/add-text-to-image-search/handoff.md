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

Confirmation 1 refused the fix, and the refusal was right one layer deeper:
per-page repeatability was observed rather than guaranteed, and a specification
may not promise what merely happens to be true of one engine. The promise is
now conditional (`fff9826`): the order is always score then identifier, a page
whose edges do not cut a group of identical scores repeats exactly, and a page
whose edge does cut one holds whichever members it got with nothing promised
about which.

Second confirmation of round 1: `/gate-review add-text-to-image-search 2
confirm 1`. If it refuses again, that is the second failed confirmation on one
finding and the protocol says stop and ask the user to arbitrate.

Local evidence: `env -u DATABASE_URL make check` green (307 tests);
`make test-integration` green (183 tests).

## Blockers

None.
