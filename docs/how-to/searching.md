# Find a picture by describing it

The service embeds your words with CLIP's text tower and ranks the stored image
vectors by cosine similarity. This is how to ask, what the answer means, and
where its edges are.

Every command here was run in the form shown against a local service with the
real CLIP weights and five pictures imported from a folder — a red field, a
green field, a blue circle, a black square and a yellow circle. The answers are
the answers it gave, with the scores rounded and the asset trimmed to the field
that names it; a real answer carries the whole asset.

## Ask

```console
$ curl -s "http://127.0.0.1:8000/api/v1/search/text?q=a+blue+circle+on+a+white+background&limit=3" | jq
{
  "items": [
    { "name": "blue-circle.png",   "score": 0.311 },
    { "name": "yellow-circle.png", "score": 0.241 },
    { "name": "black-square.png",  "score": 0.18 }
  ],
  "limit": 3,
  "offset": 0,
  "has_more": true,
  "model": "clip-vit-l14",
  "query_truncated": false
}
```

An item is the asset exactly as every other endpoint returns it, plus a score:

```console
$ curl -s "http://127.0.0.1:8000/api/v1/search/text?q=a+solid+red+background&limit=1" | jq '.items[0]'
{
  "score": 0.248,
  "asset": {
    "id": "e7a141b9-9cc3-4b9f-b0a3-2cd0e32a8705",
    "original_filename": "red-field.png",
    "tags": ["demo"],
    "index_status": { "clip-vit-l14": "done" }
  }
}
```

## What a score is, and is not

`score = 1 − cosine distance`, so 1 is identical and 0 is unrelated. **It is
comparable only within one model and only within one query.** CLIP's
text–image scores are not spread over the whole range: in the run above, the
best match of a good query scored 0.311 and the worst picture in the same
ranking scored 0.18. That is normal — the useful signal is the *order* and the
gap between neighbours, not the absolute number.

This is why the answer states `model`: a score from `clip-vit-l14` says nothing
about a score from any other model, and comparing them is meaningless.

There is no notion of "no match". A search always returns an order; a threshold
is how you say that the tail is not worth showing.

## Page through it

`limit` defaults to 20 and is at most 100; `offset` starts at 0. `has_more`
comes from looking one result beyond the page, so it is exact rather than an
estimate, and there is no total — with an approximate index a count would cost
a full scan and be stale when it arrived.

```console
$ curl -s "http://127.0.0.1:8000/api/v1/search/text?q=a+blue+circle+on+a+white+background&limit=3&offset=3" | jq
{
  "items": [
    { "name": "red-field.png",   "score": 0.177 },
    { "name": "green-field.png", "score": 0.177 }
  ],
  "offset": 3,
  "has_more": false
}
```

Results with the same score are ordered by the asset's identifier, so a page is
never ambiguous about its own arrangement, and asking again for a page whose
edges do not cut through equal scores gives the same items. A group of
*identical* scores that does not fit on one page is the exception: which of its
members a page holds is the index's choice, so paging through such a group can
repeat or skip one, and repeating the request is not promised to give the same
members either. Two pictures do not have to be the same picture for that: any
two vectors at the same angle to the query score the same. It stays rare with a
real model and a real corpus, and the answer when it happens is to ask for a
page large enough to hold the group — an approximate index may not return the
whole group at all, whatever page you ask for.

`limit + offset` may not exceed 1000. Beyond that the index cannot answer
accurately at all, so the request is refused rather than answered worse:

```console
$ curl -s "http://127.0.0.1:8000/api/v1/search/text?q=dragon&limit=100&offset=901"
{"type":"/errors/page-too-deep","title":"Unprocessable Entity","status":422,
 "detail":"limit + offset must be at most 1000, got 1001","instance":"urn:request:…"}
```

## Cut off the tail

`min_score` drops results below it **after** ranking. The page it produces is
shorter rather than reaching further down the ranking, and the next page still
starts where this one ended:

```console
$ curl -s "http://127.0.0.1:8000/api/v1/search/text?q=a+green+field+of+grass&limit=5&min_score=0.15" | jq
{
  "items": [
    { "name": "green-field.png", "score": 0.206 }
  ],
  "has_more": false
}
```

Without the threshold that same query returns all five pictures, scoring 0.206,
0.147, 0.137, 0.129 and 0.124 — which is a good illustration of why the
threshold is a per-model, per-corpus judgement rather than a universal number.
Start without it, look at the scores you actually get, then choose.

## What is refused

| Answer | When |
|---|---|
| 422 `/errors/invalid-query` | `q` is missing, empty, or only whitespace |
| 422 `/errors/validation` | `q` is longer than 256 characters, `limit` is outside 1–100, `offset` is negative, or `min_score` is outside [−1, 1] |
| 422 `/errors/page-too-deep` | `limit + offset` is beyond 1000 |
| 503 `/errors/model-unavailable` | this build does not run the search model, so nothing can embed the query |

```console
$ curl -s "http://127.0.0.1:8000/api/v1/search/text?q=+"
{"type":"/errors/invalid-query","title":"Unprocessable Entity","status":422,
 "detail":"q must not be empty","instance":"urn:request:…"}
```

## What the corpus looks like

Two views answer "what is in there" and "is indexing keeping up":

```console
$ curl -s http://127.0.0.1:8000/api/v1/tags | jq
{
  "items": [
    { "tag": "demo", "assets": 5 }
  ],
  "limit": 100
}

$ curl -s http://127.0.0.1:8000/api/v1/stats | jq
{
  "assets": 5,
  "stored_bytes": 11878,
  "work": [
    { "model": "clip-vit-l14", "status": "done", "jobs": 5 }
  ],
  "oldest_waiting_seconds": null
}
```

`stored_bytes` is the size of the originals as the assets record it —
thumbnails are not counted, and nothing walks the media root to produce it.
`oldest_waiting_seconds` is absent rather than zero when nothing is waiting.

## What this search does not do yet

- **Filters.** `tags_all`, `tags_any` and metadata filters belong inside the
  vector query rather than beside it, which is a different question with its
  own measurement; until that change lands, narrow a corpus with the listing
  (`GET /api/v1/assets?tags_all=…`) rather than with the search.
- **Pictures as queries.** Searching by an image, and "more like this" for a
  stored asset, arrive with DINOv2.
- **Other languages.** CLIP ViT-L/14 was trained on English captions; other
  languages degrade towards a random ranking. The service does not translate,
  and says so rather than pretending.
- **A promise about recall.** A deep page is *searched* as deeply as it asks —
  `hnsw.ef_search` is raised per query to `limit + offset` — but how close an
  approximate ranking is to an exact one is measured in its own change, not
  asserted here.

An asset is findable as soon as it has a vector, and stays findable while a
re-index is queued: the vector it has answers until a new one replaces it. What
the queue is doing is in [`indexing.md`](indexing.md).
