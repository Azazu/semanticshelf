# Find a picture by describing it

**Risk-Tier:** medium

## Why

Everything built so far exists for this: a picture is stored, inspected,
queued, embedded, and its vector sits in an index nobody has ever queried. The
service can answer "which pictures do you have" and not "which picture is the
blue dragon". This change asks the question.

It is also the first time the two halves of CLIP meet: the image tower has been
filling the store since change 4, and the text tower has been sitting unused
behind the same protocol. A text query goes through it, and the result is
ranked by the cosine similarity the index was built for.

## What Changes

- New endpoint `GET /api/v1/search/text?q=…&limit&offset&min_score`: the query
  is embedded with the CLIP text tower on the inference pool, and the nearest
  assets by cosine similarity of their `clip-vit-l14` vectors come back ranked.
- An item is the asset representation the rest of the API returns, plus
  `score = 1 − cosine distance` in [−1, 1]. Every page is ordered by score and
  then by identifier, so what a page holds is never ambiguous about its
  arrangement; a page across which no group of identical scores falls repeats
  exactly while the index is unchanged, and a page whose edge cuts such a group
  carries whichever members it got, with nothing promised about which.
- The envelope is `{items, limit, offset, has_more, model, query_truncated}`:
  no total, `has_more` from fetching one candidate beyond the page, the model
  key stated because a score means nothing without it, and `query_truncated`
  because CLIP cuts a query at 77 tokens and an answer to a shortened question
  should say so.
- `min_score` drops items below a threshold **after** ranking, so a filtered
  page may be shorter than `limit` and the next page still starts where this
  one ended. Nothing backfills.
- Every search sets `hnsw.ef_search` for its transaction to
  `max(HNSW_EF_SEARCH, limit + offset)` so a deep page does not silently lose
  recall, and a page beyond 1 000 is refused with 422 `page-too-deep` — the
  bound pgvector itself has. New setting `HNSW_EF_SEARCH` (default 40).
- The vector query keeps the cast and the model predicate ADR-001 requires, now
  with an offset; a plan-reading test keeps it honest, because losing either
  turns an index scan into a sequential one with no other symptom.
- `GET /api/v1/tags` (tag counts, ordered by count then name) and
  `GET /api/v1/stats` (assets, work per model and state, the age of the oldest
  waiting job, bytes under the media root): the two read-only views the demo UI
  of change 10 needs, and the fastest way for an operator to see whether
  indexing is keeping up.
- FR-TXT-3 says only assets whose CLIP job is `done` may appear. What the store
  can answer is "has a vector for that model", and the two differ after a
  reset: `reindex` puts the work back but leaves the last vector in place. The
  requirement is amended to say what the service does — an asset appears while
  it has a vector, and a re-run replaces that vector rather than hiding it —
  because hiding it would mean an asset dropping out of search for as long as
  its work is queued.

## Non-goals

- `tags_all`, `tags_any` and `meta.<key>` on search. FR-FLT-2 puts them inside
  the vector query, which is a filtered-HNSW question with its own measurement;
  change 12 owns it, and this change deliberately ships search without filters
  rather than with the wrong kind of filter.
- Image→image search, `/similar`, DINOv2 and the `model` parameter (change 11).
  The only model with a text tower is CLIP, so the endpoint names it in the
  answer and takes no choice.
- Any change to how vectors are produced or stored, to the queue, or to the
  upload and import paths.
- Query preprocessing: no stemming, no spell-checking, no translation. The
  query goes to CLIP as the caller wrote it, and the README says the model is
  English (FR-TXT-5).
- Measuring recall or latency. ADR-002 and `tune-vector-indexes` (change 14)
  own that; this change states what it does not know.

## Capabilities

### New Capabilities

- `text-search`: the search endpoint — what a query may be, how results are
  ranked and scored, what the envelope says, how a threshold and a page
  interact, and what makes a page too deep.
- `service-stats`: the operational view of the store — how much is indexed,
  how much is waiting, how old the oldest waiting work is, and how much disk
  the pictures take.

### Modified Capabilities

- `asset-api`: the resource surface gains the tag census the UI's tag cloud
  and filter list are built from.
- `embedding-storage`: the nearest-neighbour lookup gains an offset and a
  distance threshold, so that a page of results and a threshold are one query
  rather than a post-filter over a fixed candidate list.

## Impact

- New: `app/api/search.py`, `app/services/search.py`, `app/schemas/search.py`,
  the `/tags` and `/stats` endpoints and their services, a how-to page.
- Changed: `app/repositories/embeddings.py` (offset, threshold, and the
  `ef_search` setting per transaction), `app/core/settings.py` (one setting),
  `docs/reference/settings.md`, `docs/explanation/requirements.md` (FR-TXT-3,
  as above).
- Unchanged: the schema and every migration — the index this change queries was
  built in change 3 and is the reason ADR-001 exists.
- No new dependency.
