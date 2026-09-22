# Handoff — add-text-to-image-search

**Updated:** 2026-09-22 · claude
**State:** awaiting-gate-2
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

The branch is pushed and its CI run is green (reported by the user), so all 30
tasks are checked. Gate 2 requested with `/gate-review add-text-to-image-search
2`; the verdict and its findings are recorded in `review.md` by the runner.

Local evidence, every check CI runs: `openspec validate --all --strict` (11
items), every `scripts/*_test.sh`, `sh -n scripts/*.sh`,
`env -u DATABASE_URL make check` (307 tests) and `make test-integration`
(181 tests) — all green. `make test-models` (12 tests, real CLIP) green too,
which is where the ranking is shown to mean something.

## Blockers

None.
