# Design — add-text-to-image-search

## Context

See `proposal.md` — Why. Everything this change needs exists: the CLIP adapter
has both towers behind one protocol (change 4), the inference pool keeps model
work off the event loop, `EmbeddingRepository.nearest` already builds the one
vector query in the service and carries the cast ADR-001 requires, and the
partial HNSW index per model has been there since change 3.

Three facts from the code shape the decisions below, each verified against the
current source rather than remembered:

| Fact | Where |
|---|---|
| `Embedder.embed_text` returns unit-length rows and a `truncated` flag per input — the flag exists precisely so a caller can pass "I answered a shorter question" on | `app/ml/base.py` |
| `nearest_statement` orders by `cast(vector, Vector(dim)).cosine_distance(q)` and filters on the model key; losing either turns the index scan into a sequential scan with no other symptom | `app/repositories/embeddings.py`, ADR-001 |
| A service function that leaves a session mid-transaction breaks the next one; this project has paid for it three times | `app/services/indexing.py`, `app/services/folder.py` |

## Goals / Non-Goals

**Goals.** One query per search that the index answers; an envelope that says
what it knows and admits what it does not; a ranking whose order is fully
determined, so a test can assert it exactly.

**Non-Goals (design level).** No caching of query vectors, no query rewriting,
no recall measurement (ADR-002 owns it), and no second model — the endpoint
names the one it used rather than taking a choice.

## Decisions

1. **The query vector is made on the inference pool, once per request.**
   `app/services/search.py` acquires the embedder through `app/ml/pool.acquire`
   and calls `embed_text` through `run_in_pool`, exactly as the indexing runner
   embeds an image. The pool is the application's, from `app.state`.
   Rejected: embedding on the event loop because "a text query is small" — a
   CLIP text pass is tens of milliseconds of CPU, and the service answers other
   requests during it.

2. **A model this build cannot run is a server-side fact, not a bad request.**
   If the search model is not enabled, the endpoint answers 503 problem details
   naming it. The store may well hold its vectors — nothing can embed the
   query, which is a fact about this deployment.
   Rejected: 422, which tells the caller to fix a query that is fine.

3. **One transaction per search, and the index's effort set inside it.**
   `SET LOCAL hnsw.ef_search = :effort` applies to the transaction, so the
   search runs inside `async with session.begin():` — set, query, commit — and
   the endpoint does no read before it. The effort is
   `max(HNSW_EF_SEARCH, limit + offset)`, never above the 1 000 pgvector
   allows, and a page whose `limit + offset` exceeds that is refused before
   anything runs.
   What this does NOT guarantee: a deep page is *searched* as deeply as it asks,
   not that its ranking equals an exact scan's. What recall that buys is
   ADR-002's question, and this change says so rather than implying an answer.

4. **The threshold is an outer filter over the page, and the page is not
   refilled.** The statement is one: an inner select ordered by distance with
   `LIMIT limit + 1 OFFSET offset` — the shape the index answers — wrapped in an
   outer select that drops rows beyond the maximum distance. A filtered page
   can therefore be shorter than `limit`, which is what FR-FLT-1 means by
   "after ranking", and the next page still starts where this one ended.
   Rejected: filtering inside the ordered select, which turns the query into a
   filtered vector search — a different problem with its own measurement
   (change 12), and one that would make `offset` mean something else.

5. **`has_more` is one row beyond the page, and the threshold makes that
   exact.** The search asks for `limit + 1` rows; if the extra one comes back,
   there is more to show. The first draft of this decision said a threshold
   must not affect `has_more` "because the next page may still hold matches" —
   which is false, and pleasantly so: the ranking is ordered by distance, so a
   row below the threshold has only rows further away after it. A threshold
   that removes the extra row therefore means there is genuinely nothing more
   to show, and `has_more` is false for the right reason rather than by
   accident.

6. **Scores are derived, distances are stored.** `score = 1 − distance`, computed
   where the row is read, so nothing but the repository ever handles a
   distance. With unit-length vectors the distance is in [0, 2] and the score in
   [−1, 1]; the API exposes the score because that is the number a client can
   reason about, and the model key beside it because the number means nothing
   without it.

7. **Ties are broken by the identifier — outside the ordered select, not in
   it.** The first attempt was `ORDER BY distance, asset_id`, and the
   plan-reading test refused it immediately: an HNSW ordering takes exactly one
   key, and a second turns the index scan into a sort over a bitmap scan. So
   the inner select orders by distance alone (the shape the index answers) and
   the outer one orders the page it returned by distance and then identifier.
   Two equally near assets therefore keep one order between requests for the
   same page; a tie that straddles a page boundary is still the index's to
   resolve, which is the same caveat pagination over an approximate index
   carries anyway.

8. **Three bounded queries per search, and no N+1.** The vector query returns
   the page's asset identifiers and their distances; one query fetches those
   assets; one more fetches their indexing states, as the listing already does.
   Everything is bounded by the page size, and the assets come back in the
   ranking's order rather than the store's.

9. **`/tags` is one aggregate, not a scan in Python.**
   `SELECT unnest(tags) AS tag, count(*) … GROUP BY tag ORDER BY count DESC, tag
   ASC LIMIT n`, with the same bounded-page discipline as everything else.

10. **`/stats` counts what the store knows, and says what it does not.** Asset
    count, work per model and state, the age of the oldest waiting job, and the
    total of the stored sizes the assets record. It does not walk the media
    root: the number it reports is the bytes of the originals as stored, and the
    thumbnails are not in it — stated in the response's documentation rather
    than left for someone to discover. Nothing is cached or kept as a running
    total, so the numbers cannot drift from the store.

11. **Both new endpoints are read-only and take the request's session**, like
    every other read in `app/api/assets.py`. The one novelty is decision 3's
    transaction, which exists for `SET LOCAL` and for nothing else.

## Risks / Trade-offs

- **A ranking that is plausible and wrong** → the deterministic fake embedder
  makes the expected order exact, so the api and integration tests assert
  positions rather than "looks reasonable". A real-model test (`-m models`,
  never in CI) searches a handful of pictures with real CLIP and asserts the
  one the words describe comes first — the only test that can catch a wiring
  error between the two towers.
- **Losing the cast or the model predicate** → the plan-reading test of change 3
  covers the repository's statement, and this change extends it to the statement
  with an offset and a threshold, because that is the statement the endpoint
  now runs. It has already earned its keep here: it caught the tie-break of
  decision 7 costing the index scan, before any of this reached a review.
- **A deep page's recall** → stated in decision 3 and left to ADR-002. The
  endpoint refuses what pgvector cannot answer at all rather than pretending.
- **`SET LOCAL` outside a transaction** silently does nothing. The search runs
  in an explicit transaction, and a test asserts the setting is in effect for
  the query rather than trusting that it was sent.
- **A session left mid-transaction** — the mistake this project has made three
  times. The search's transaction is opened and closed in one place, and a test
  asserts the session is clean afterwards.

## Migration Plan

None. No schema change, no migration, no setting that changes an existing
default; `HNSW_EF_SEARCH` is new and has one.

## Open Questions

None.
