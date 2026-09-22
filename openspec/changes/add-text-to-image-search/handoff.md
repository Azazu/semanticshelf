# Handoff — add-text-to-image-search

**Updated:** 2026-09-22 · claude
**State:** awaiting-gate-2
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

Gate 2 round 2 returned two majors, both fixed:

- The 256-character bound was a `max_length` on the raw parameter while
  FR-TXT-2 bounds the *trimmed* query, so a query padded with one space and
  256 characters was refused for a length it did not have. The bound now lives
  in `normalised_query` in the service; the parameter keeps a far larger guard
  (1024) so padding cannot make a request unbounded, which is what NFR-SEC-5
  asks for. Demonstrated: restoring the `max_length` makes the new api test
  fail.
- The operation answered 503 without declaring it. The route now declares it
  with `problem_responses(503)`, and an api test asserts the document carries
  200, 422, 500 and 503, the last with the problem media type.

Swept with them: the spec's query requirement and a scenario for the padded
case, design decision 2, tasks 3.2 and the new 3.8, FR-TXT-2's neighbour
NFR-SEC-5, and the how-to's refusal table (the length case is
`/errors/invalid-query` now, and the raw guard is named as a guard).

Run: `/gate-review add-text-to-image-search 2 confirm 2`.

Local evidence: `make check` green (324 tests), `make test-integration` green
(183 tests), `openspec validate --all --strict`, both `scripts/*_test.sh`,
`sh -n` over `scripts/*.sh`.

## Blockers

None. The code changed after the push, so the user pushes again and reports CI
before the merge.
