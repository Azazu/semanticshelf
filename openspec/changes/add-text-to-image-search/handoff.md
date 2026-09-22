# Handoff — add-text-to-image-search

**Updated:** 2026-09-22 · claude
**State:** implementing
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

**Gate 1 passed** (Confirmation 2 of round 1, commit `7ba8202`, all four
findings confirmed). The contract is settled: the page carries a total order,
membership at a tie-cutting edge belongs to the approximate index, the page
depth ends at 999 so the `has_more` sentinel is always obtainable, `/stats`
means the recorded sizes of the originals, and the three new operations carry
OpenAPI examples.

Gate 2 needs a **full round**, not a confirmation of its round 1: the code
changed after that round (the depth bound, the three examples). Before it can
be requested, two things that are not mine:

1. The repository-root settings file has to come back, so the integration suite
   runs instead of skipping (see Blockers).
2. The user pushes `change/add-text-to-image-search` and reports the CI run on
   the exact HEAD.

Then: `/gate-review add-text-to-image-search 2`.

Local evidence so far: `make check` green (314 tests), `openspec validate --all
--strict`, both `scripts/*_test.sh`, `sh -n` over `scripts/*.sh`. The how-to's
refusal example was re-captured from a running service.

## Blockers

The repository-root settings file the integration suite reads is absent on this
machine (only the example beside it remains), so `make test-integration` skips
all 183 tests instead of running them. The container is up and listening on
port 5434. Restoring it is the user's action; the Definition of Ready for
Gate 2 needs that suite green.
