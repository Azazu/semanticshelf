# Handoff — add-text-to-image-search

**Updated:** 2026-09-22 · claude
**State:** awaiting-gate-1
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

Gate 1 round 1 returned two blockers and two majors, all fixed in `28feebe`:
the storage delta now carries the same bounded tie guarantee as the search
contract; the page bound and the `has_more` sentinel are one rule
(`MAX_PAGE_DEPTH = MAX_SEARCH_EFFORT - 1`, so a page reaches 999) with a unit
test that fails when the bound is raised back; `/stats` is described one way
everywhere (the recorded sizes of the originals); and all three new operations
carry an OpenAPI example that the suite parses with its own model. FR-FLT-4,
FR-FLT-5 and the roadmap were amended with them.

Run: `/gate-review add-text-to-image-search 1 confirm 1`. After Gate 1 settles,
Gate 2 needs a fresh round rather than a confirmation of its round 1 — the code
changed here (the depth bound, three examples), so the user pushes and reports
CI first.

Local evidence: `make check` green (314 tests), `openspec validate --all
--strict`, both `scripts/*_test.sh`, `sh -n` over `scripts/*.sh`. The how-to's
refusal example was re-captured from a running service.

## Blockers

The repository-root settings file the integration suite reads is absent on this
machine (only the example beside it remains), so `make test-integration` skips
all 183 tests instead of running them. The container is up on port 5434. This
round changed no SQL, but the suite has to run green before Gate 2.
