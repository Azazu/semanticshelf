# Handoff — add-text-to-image-search

**Updated:** 2026-09-22 · claude
**State:** merged
**Branch:** change/add-text-to-image-search

## Done this session

Task groups 1-6 complete; 28 of 30 tasks checked.

- `EmbeddingRepository.nearest` takes a page and a maximum distance in three
  layers: the window the index answers (`ORDER BY distance`, `LIMIT limit +
  offset`), the page cut from it once the order is total (`ORDER BY distance,
  asset_id`, then the offset and the limit), and the distance filter outside
  both.
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

Confirmation 2 kept finding 1 open on coherence rather than on the mechanism:
the promise was conditional in the spec and the how-to, and still
unconditional in `proposal.md`. `496e708` states one contract in every artifact
that names it — proposal, FR-TXT-3, design decisions 4 and 7, tasks 1.1 and
1.3, and the repository docstring, which claimed the identifier is the
tie-break "for the whole ranking" rather than down to the end of the page. No
behavior changed.

## Next step

Merged into `main` as `f2052df` (`--no-ff`, 34 commits) after the verifier
passed, and archived with the four spec deltas synced into `openspec/specs/`:
`text-search` and `service-stats` are new capabilities, `asset-api` gained the
tag census and `embedding-storage`'s nearest-neighbour requirement gained the
page, the threshold and the bounded tie rule.

Next in the roadmap: change 9, `add-demo-dataset`.

## Blockers

None.
