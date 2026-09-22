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

Gate 1 again, on the contract rather than on the code. Confirmation 3 refused
round 1 a third time and made two points: the rarity argument was false
(distinct vectors can share a cosine distance exactly — demonstrated), and the
revised promise is a requirements change that belongs at Gate 1. The first is
fixed in `ec44d6a`; the second the user arbitrated on 2026-09-22 — reopen
Gate 1.

What Gate 1 now reviews: `specs/text-search/spec.md` promises a total order on
every page and no more, and design decision 7 carries the measurement behind
it. On a probe of 10 000 random unit vectors plus five distinct unit vectors at
one exact distance, forced onto the index and asked for a thousand rows, HNSW
returned 1 of the 5 tied rows at `ef_search = 40` and all 5 at 100 and 1000.
The search effort decides which equally distant rows exist to be ordered, the
window cannot, and `ef_search` is a heuristic — so a global tie-break on the
identifier is not available short of an exact scan.

Run: `/gate-review add-text-to-image-search 1`. Gate 2 confirmation of round 1
follows once Gate 1 settles the contract.

Local evidence: `make check` green (307 tests), `openspec validate --all
--strict`, both `scripts/*_test.sh`, `sh -n` over `scripts/*.sh`.

## Blockers

The repository-root settings file the integration suite reads is absent on this
machine (only the example beside it remains), so `make test-integration` skips
all 183 tests instead of running them. It was present earlier in this change —
its last green run covered the statement this round only documents. Restoring
it is the user's action; nothing in this round touches SQL.
