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

   Because that 503 belongs to this operation rather than to the application,
   the route declares it (`problem_responses(503)`) — FR-OPS-4 asks for the
   problem-details responses per status code, and the factory only declares the
   422 and 500 every operation can answer. Gate 2 caught it missing.

3. **One transaction per search, and the index's effort set inside it.**
   `SET LOCAL hnsw.ef_search = :effort` applies to the transaction, so the
   search runs inside `async with session.begin():` — set, query, commit — and
   the endpoint does no read before it. The effort is
   `max(HNSW_EF_SEARCH, limit + offset + 1)`, never above the 1000 pgvector
   allows, and a page is refused before anything runs when `limit + offset`
   passes **999**.

   That odd-looking bound is the whole point of the `+ 1`. An HNSW scan yields
   at most `ef_search` rows — measured, not assumed: at `ef_search = 40` a
   query asking for a thousand rows got exactly forty. One of those rows is the
   sentinel that answers `has_more` (decision 5), so a page reaching depth 1000
   would need candidate 1001 of 1000 and could only guess. Gate 1 caught this:
   the first draft bounded the page at 1000 and set the effort to
   `limit + offset`, which under-provisions the sentinel on every deep page and
   makes it unobtainable at the boundary. `MAX_PAGE_DEPTH = MAX_SEARCH_EFFORT -
   1` ties the two together, and the unit test
   `test_the_deepest_page_the_service_answers_still_has_its_sentinel` fails if
   the page bound is raised back to the index's ceiling.

   What this does NOT guarantee: a deep page is *searched* as deeply as it asks,
   not that its ranking equals an exact scan's. What recall that buys is
   ADR-002's question, and this change says so rather than implying an answer.

4. **The threshold is an outer filter over the page, and the page is not
   refilled.** The statement is one, in the three layers decision 7 settles:
   the window the index answers, the page cut from it once the order is total,
   and outside both a filter that drops rows beyond the maximum distance. A
   filtered page can therefore be shorter than `limit`, which is what FR-FLT-1
   means by "after ranking", and the next page still starts where this one
   ended. The `limit + 1` that answers `has_more` belongs to the service rather
   than to the statement: it asks for one row beyond the page (decision 5), and
   the window grows with it.
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

7. **The page is cut after the order is total, and the window is the page's
   own size.** This decision took three shapes, and the last two are worth
   keeping written down.

   `ORDER BY distance, asset_id` inside the ordered select was the first, and
   the plan-reading test refused it at once: an HNSW ordering takes exactly one
   key, and a second turns the index scan into a sort over a bitmap scan.

   Cutting the page in that select and ordering afterwards was the second, and
   Gate 2 refused it: the index then chooses which of several equally distant
   rows the page contains, and the identifier can only sort what it was handed.
   So there are three layers now — a window the index answers (`ORDER BY
   distance`, `LIMIT offset + limit`), the page cut from it once the order is
   total (`ORDER BY distance, asset_id`, then `OFFSET`/`LIMIT`), and the
   threshold outside that.

   What remains, and is now stated rather than implied: which equally distant
   rows enter the window at all is the index's choice. Measured on five assets
   sharing one vector, paged two at a time, the three pages repeated one member
   and skipped another — while each page on its own answered identically five
   times over.

   That last observation is where the confirmation caught the specification
   overreaching: this engine answers a tie-cutting page the same way every time,
   but nothing makes it do so, and a specification may not promise what only
   happens to be true. So the promise is now conditional — a page across which
   no group of identical scores falls repeats exactly; a page whose edge cuts
   such a group carries whichever members it got, in identifier order, and the
   service says nothing about which. The test that observes the repetition
   remains, labelled as a record of what this engine does rather than as a
   contract.
   Two arguments were offered for leaving that edge open, and the third
   confirmation destroyed one of them and the measurement behind it destroyed
   the need for the other.

   The wrong one was rarity: "a tie needs two pictures whose vectors match to
   the last bit". That is false. A tie needs only two vectors at the same angle
   to the query, and nothing ties their tails together. Built on the probe
   database — 10 000 random unit vectors plus five *distinct* unit vectors each
   carrying 0.6 in the first slot and 0.8 in a different one — all five sit at
   cosine distance `0.3999999761581421` from the one-hot query, exactly and
   reproducibly. Distinct vectors, one distance.

   The remaining one is cost, and it is the wrong question. Taking the whole
   searchable depth as the window costs **18.3 ms against 0.2 ms** on 10 000
   vectors at `ef_search = 1000`, ninety times the price on every search
   including the first page of twenty — but it would not buy the guarantee
   anyway. On that same probe, forced onto the index (`enable_seqscan = off`)
   and asked for a thousand rows:

   | `hnsw.ef_search` | rows the index returned | of the five tied rows |
   |---|---|---|
   | 40 (the default) | 40 | **1** |
   | 100 | 100 | 5 |
   | 1000 | 1000 | 5 |

   At the default effort four of the five nearest neighbours are not in the
   candidate set at all. No window can order rows the index never returned, and
   no `FETCH FIRST … WITH TIES` can either — tried on the same data, it stopped
   at four rows because the fifth tied row was not there to tie with. The
   effort, not the window, decides; and `ef_search` is a heuristic, not a
   promise. A global tie-break on the identifier is therefore not a thing an
   approximate index can offer at any price short of an exact scan — which is
   the one thing this index exists to avoid.

   So the specification says the strongest true thing and stops: the order on a
   page is total, a page whose edge does not cut a group of identical scores
   repeats exactly, and which members of such a group a page holds belongs to
   the index. That is not a weakening for convenience; it is what an
   approximate nearest-neighbour search is.

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
