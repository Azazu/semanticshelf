## 1. The vector query grows a page and a threshold

- [x] 1.1 Extend `EmbeddingRepository.nearest_statement` and `nearest` with an offset and a maximum distance, as the one statement of design decisions 4 and 7: a window ordered by distance alone down to the end of the page — the shape the index answers — the page cut from it by an outer select that breaks ties by identifier before applying the offset and the limit, and the distance filter outside both. The cast and the model predicate stay exactly as ADR-001 requires. Verify: `tests/integration/test_embedding_storage.py` gains tests for the offset (with no equal distances across its boundary, the tail of the unpaged answer, same order), for the maximum distance (nothing beyond it, and the count is not refilled), and for the two together.
- [x] 1.2 The plan of the new statement is still an index scan, not a sequential one. Verify: the existing plan-reading test is extended to the statement the endpoint runs — with an offset and a threshold — and asserts the model's index by name.
- [x] 1.3 Ties are broken by the asset identifier in SQL, before the page is cut out of the window (design decision 7), so a page whose edge does not cut a group of equal distances holds the same items every time; which members of a group the window itself holds stays the index's choice. Verify: an integration test with two assets at an identical distance asserts the same order over repeated queries, and one paging through a group larger than the page records what this engine does without promising it.
- [x] 1.4 Add `HNSW_EF_SEARCH` to `app/core/settings.py` (default 40, positive, at most 1000). Verify: `tests/unit/test_settings_search.py` asserts the default by value, refuses zero and refuses a value above the maximum, and reads it from the environment.

## 2. The search itself

- [x] 2.1 Write `app/services/search.py`: embed the query through the inference pool, open one transaction, set `hnsw.ef_search` to `max(HNSW_EF_SEARCH, limit + offset + 1)` — the row beyond the page included, because that row is `has_more` — run the vector query, and return the hits with their scores and whether more exist (design decisions 1, 3, 4, 5). Verify: unit tests with the fake embedder cover the score arithmetic, the truncation flag and the `has_more` rule; the integration tests of section 3 cover the query.
- [x] 2.2 A search model this build does not run is refused with 503 problem details naming it, before any query runs (design decision 2). Verify: an api test with an empty `ENABLED_MODELS`.
- [x] 2.5 No api test can load a real checkpoint: the suite replaces the CLIP factory with the fake, as the integration suite does. The first search test written here loaded real weights, which in CI would have been a download. Verify: `tests/api/conftest.py` holds the autouse fixture, and the suite passes with `HF_HUB_OFFLINE=1` and an empty model cache.
- [x] 2.3 The search's transaction is opened and closed in one place, and the session is clean afterwards. Verify: an integration test asserts `session.in_transaction()` is false after a search, and that a second search on the same session works.
- [x] 2.4 The assets of a page are fetched in one query and returned in the ranking's order, with their indexing states, as the listing does (design decision 8). Verify: an integration test asserts the order and that the number of queries does not grow with the page size.

## 3. The endpoint

- [x] 3.1 Add `app/api/search.py` with `GET /api/v1/search/text`, mounted by the app factory, and `app/schemas/search.py` for the item and the envelope (`items`, `limit`, `offset`, `has_more`, `model`, `query_truncated`). Verify: an api test asserts the shape of an answer, and `GET /api/openapi.json` lists the operation with its summary and description.
- [x] 3.2 Query validation: required, non-empty after trimming, at most 256 characters; 422 problem details naming the parameter otherwise. Verify: api tests for a missing query, an empty one, one of only spaces, and one a character too long.
- [x] 3.3 Pagination: `limit` default 20 and at most 100, `offset` at least 0, and `limit + offset` beyond 999 refused with 422 `page-too-deep` before anything is searched. Verify: api tests for each bound, including the page that is exactly at the bound and the one a single item beyond it.
- [x] 3.4 `min_score` drops items below it and does not refill the page; `has_more` still reflects the ranking (design decisions 4 and 5). Verify: integration tests for a threshold that removes some of a page, for one nothing reaches, and for a page that is short while more results exist.
- [x] 3.5 A truncated query answers normally and says so. Verify: an integration test with a query longer than the model's context asserts `query_truncated` is true and that results still come back.
- [x] 3.6 An asset appears exactly while it has a vector for the model: an asset whose work was reset but whose vector remains is still found, and one that has never been indexed is not (the amendment of task 6.3). Verify: integration tests for both.
- [x] 3.7 The two bounds are one rule: the deepest accepted page still leaves the index a candidate for the row that answers `has_more` (`MAX_PAGE_DEPTH = MAX_SEARCH_EFFORT - 1`, design decision 3). Verify: `tests/unit/test_search_policy.py` asserts that `effort_for` covers `limit + offset + 1` for the deepest page `check_depth` accepts, and fails when the page bound is raised back to the index's ceiling — demonstrated.

## 4. The two views the UI needs

- [x] 4.1 `GET /api/v1/tags`: tags in use with their counts, ordered by count then tag, `limit` default 100 and at most 500, 422 beyond it. Verify: integration tests for the order, for a tie broken by the tag, for a tag that disappears when its last asset is deleted, and for the bound.
- [x] 4.2 `GET /api/v1/stats`: asset count, work per model and state, the age of the oldest waiting job (absent when nothing waits), and the total stored bytes of the originals (design decision 10). Verify: integration tests for a store with work in every state and for an empty store.
- [x] 4.3 Both endpoints are documented in the OpenAPI document with a summary and a description, and `/stats` says in its description that the byte total counts the originals and not the thumbnails. Verify: an api test reads the document.
- [x] 4.4 All three operations this change adds — `GET /search/text`, `GET /tags`, `GET /stats` — carry a response example in the OpenAPI document, as FR-OPS-4 requires of every operation. The examples are the answers of the run recorded in `docs/how-to/searching.md` (the `/stats` one with a job still waiting, because an example field that is `null` is dropped from the document). Verify: `tests/api/test_openapi_examples.py` finds each example under its operation and parses it with the response model it illustrates, so an example that drifts from the schema fails the suite.

## 5. Evidence that the ranking is right

- [x] 5.1 The order a search returns is asserted exactly, not approximately: with the fake embedder's deterministic vectors, a fixture of assets has one known correct ranking. Verify: an integration test asserts the full order of a page, and the next page's.
- [x] 5.2 Model isolation at the endpoint: an asset with a vector under another model only does not appear. Verify: an integration test with vectors under two models.
- [x] 5.3 A real-model smoke test (`-m models`, never in CI): a handful of pictures indexed with real CLIP, and a query in words that describes one of them ranks it first. Verify: `uv run pytest -m models` output recorded in the commit body.
- [x] 5.4 `SET LOCAL hnsw.ef_search` is in effect for the query rather than merely sent. Verify: an integration test reads `current_setting('hnsw.ef_search')` inside the search's transaction and asserts the value the request implies.

## 6. Documentation

- [x] 6.1 Write `docs/how-to/searching.md`: the query, the envelope, the score and what it means, `min_score`, paging and the depth bound, what is not yet filterable (change 12), and the English-only caveat of FR-TXT-5. Verify: every command run in its exact form, output pasted from the run, the file re-read whole afterwards.
- [x] 6.2 Extend `docs/reference/settings.md` with `HNSW_EF_SEARCH` and `docs/reference/commands.md` if the endpoints add any. Verify: both re-read whole.
- [x] 6.3 Amend FR-TXT-3 in `docs/explanation/requirements.md`: an asset is searchable while it has a vector, not while its job reads `done`, because a reset leaves the vector in place (proposal). Verify: `rg "job is \`done\`" docs/` shows no surviving claim to the contrary.
- [x] 6.4 The docs index lists the new how-to, and `docs/README.md` is re-read whole. Verify: the link resolves.

## 7. Wrap-up

- [x] 7.1 Commits per logical block, no agent trailers, each body naming the evidence for the tasks its diff holds. Verify: `git log --format=%B main..HEAD | grep -c '^Co-Authored-By'` prints `0`.
- [x] 7.2 `env -u DATABASE_URL make check` green and `make test-integration` green against pgvector. Verify: both outputs recorded in a commit body.
- [x] 7.3 Acceptance on GitHub (the user pushes the branch): both jobs green. Verify: the user reports the run.
- [x] 7.4 `openspec validate add-text-to-image-search --strict` and `scripts/pregate-verify.sh gate2 add-text-to-image-search` pass; request Gate 2 with `/gate-review add-text-to-image-search 2`.
