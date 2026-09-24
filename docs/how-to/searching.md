# Find a picture

Three ways to ask the same store. **Words** find what a picture is *about*:
they are embedded with CLIP's text tower and compared with the stored image
vectors of the same model. **A picture** finds what *looks like* it: DINOv2
describes appearance rather than subject, and the query may be a file you send
or a picture the store already holds. Every answer is the same shape, and a
score only ever means something within one model.

Every command here was run in the form shown against a local service with the
real weights. The answers are the answers it gave, with the scores rounded and
each asset trimmed to the fields that identify it; a real answer carries the
whole asset.

Two corpora, because the examples came from two runs:

- the **words** examples use five pictures imported from a folder — a red
  field, a green field, a blue circle, a black square and a yellow circle;
- the **picture** examples, and every narrowing example, use the demo corpus
  (`make demo`), twenty photographs from COCO val2017 — each tagged with the
  labels COCO gives it and carrying its dataset, licence and source address as
  metadata.

The service listens on `APP_PORT`, 8000 by default; the picture and narrowing
examples were captured with `APP_PORT=8010` because 8000 was taken on that
machine. Where a compact one-line answer is too wide for the page it is wrapped,
and an identifier or a licence address in a URL is shortened with `…`; in the
narrowing examples each asset is trimmed to its tags, because that is what the
filter is about. Nothing else about an answer is touched.

## Ask with words

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

That run had one model enabled; with both, `index_status` carries a key for
each — it is the state of the asset's work, not of the search.

## Ask with a picture

`POST /api/v1/search/image` takes the picture as a multipart `file` part, with
the page fields beside it as form fields. It is accepted under exactly the rules
an upload is accepted by — the format is decided from the bytes, and the same
size and dimension bounds apply — and it is **never stored**: no asset is
created for it, nothing is written under the media root, and nothing of it
outlives the request.

```console
$ curl -s -X POST "http://127.0.0.1:8010/api/v1/search/image" \
    -F "file=@.data/demo/pictures/297343/000000297343.jpg" -F "limit=4" \
    | jq '{items: [.items[] | {name: .asset.original_filename, tags: .asset.tags,
                               score: (.score * 1000 | round / 1000)}], has_more, model}'
{
  "items": [
    { "name": "000000297343.jpg", "tags": ["stop-sign"], "score": 1     },
    { "name": "000000122745.jpg", "tags": ["stop-sign"], "score": 0.37  },
    { "name": "000000058636.jpg", "tags": [],            "score": 0.356 },
    { "name": "000000006818.jpg", "tags": ["toilet"],    "score": 0.186 }
  ],
  "has_more": true,
  "model": "dinov2-large"
}
```

The query here was a picture the corpus already holds, which is why the first
result scores 1: a vector is identical to itself. The second is the other stop
sign — found by how it *looks*, with nothing about the query touching its tags.

## The pictures like this one

`GET /api/v1/assets/{id}/similar` asks the same question about a picture the
store already holds. It costs **no inference at all** — the vector is already
there — which is also what makes it answerable on a build whose weights were
never downloaded. The asset is never among its own neighbours, at any page:

```console
$ curl -s "http://127.0.0.1:8010/api/v1/assets/e75e85e2-a011-46d6-bd27-02096645e7d8/similar?limit=3" \
    | jq -c '{items: [.items[] | {name: .asset.original_filename, tags: .asset.tags,
                                  score: (.score * 1000 | round / 1000)}], has_more, model}'
{"items":[{"name":"000000122745.jpg","tags":["stop-sign"],"score":0.37},
          {"name":"000000058636.jpg","tags":[],"score":0.356},
          {"name":"000000006818.jpg","tags":["toilet"],"score":0.186}],
 "has_more":true,"model":"dinov2-large"}
```

That is the answer above without its first row, which is the whole difference
between the two endpoints.

`limit + offset` may not exceed **998** here, one less than the other searches
allow. The index answers at most 1000 candidates; this search spends one of them
on the asset it must leave out and one on the row that answers `has_more`, so
the last page it can answer honestly ends one page earlier:

```console
$ curl -s "http://127.0.0.1:8010/api/v1/assets/e75e85e2-…/similar?limit=100&offset=899"
{"type":"/errors/page-too-deep","title":"Unprocessable Entity","status":422,
 "detail":"limit + offset must be at most 998, got 999","instance":"urn:request:…"}
```

### When an asset has no vector yet

Then there is nothing to rank it against, and that is **409, not an empty
page**: nothing is known about what it looks like, which is not the same as
nothing being like it.

```console
$ curl -s "http://127.0.0.1:8010/api/v1/assets/1fd9b2f9-e352-4e11-84fd-3396a6b104ee/similar"
{"type":"/errors/not-indexed","title":"Conflict","status":409,
 "detail":"asset 1fd9b2f9-e352-4e11-84fd-3396a6b104ee has no 'dinov2-large' vector yet",
 "instance":"urn:request:…"}
```

A corpus imported before the model was enabled is the usual reason, and one
command fills those in — it queues the work that is missing and then carries it
out:

```console
$ uv run semanticshelf index missing --model dinov2-large
model: dinov2-large
queued: 1
skipped (failed work): 0
indexed: 1
still queued: 0
failed: 0

$ curl -s "http://127.0.0.1:8010/api/v1/assets/1fd9b2f9-e352-4e11-84fd-3396a6b104ee/similar?limit=2" \
    | jq -c '{items: [.items[] | {name: .asset.original_filename,
                                  score: (.score * 1000 | round / 1000)}], model}'
{"items":[{"name":"000000058636.jpg","score":0.698},
          {"name":"000000226111.jpg","score":0.464}],"model":"dinov2-large"}
```

Work that already **failed** is not queued again by that command: an explicit
`POST /api/v1/assets/{id}/reindex` is what runs it, and `index missing` reports
how many assets it passed over for that reason rather than retrying them
quietly.

## Which model answers

Every search takes `model`. The default is the model that kind of query is
answered by — `clip-vit-l14` for words, `dinov2-large` for pictures — and
naming another one is how you compare them:

| What you ask | What happens |
|---|---|
| a model this deployment runs, that takes this kind of query | it answers, and the answer names it |
| a model with no text tower, asked for words | 422, naming what that model *can* be asked |
| a model this build does not run, or a key that does not exist | 503, naming it — the request was fine, this deployment cannot serve it |

```console
$ curl -s "http://127.0.0.1:8010/api/v1/search/text?q=a+stop+sign&model=dinov2-large"
{"type":"/errors/wrong-modality","title":"Unprocessable Entity","status":422,
 "detail":"model 'dinov2-large' takes pictures, not text","instance":"urn:request:…"}

$ curl -s "http://127.0.0.1:8010/api/v1/assets/e75e85e2-…/similar?model=dinov3-huge"
{"type":"/errors/model-unavailable","title":"Service Unavailable","status":503,
 "detail":"model 'dinov3-huge' is not enabled in this build","instance":"urn:request:…"}
```

There is no fallback to another model, ever. A score from `clip-vit-l14` and a
score from `dinov2-large` are numbers from different spaces: comparing them, or
mixing their results into one ranking, would be meaningless, and the query is
always embedded by the model whose stored vectors are searched.

## What a score is, and is not

`score = 1 − cosine distance`, so 1 is identical and 0 is unrelated. **It is
comparable only within one model and only within one query.** CLIP's
text–image scores are not spread over the whole range: in the words run above,
the best match of a good query scored 0.311 and the worst picture in the same
ranking scored 0.18. That is normal — the useful signal is the *order* and the
gap between neighbours, not the absolute number.

DINOv2's scores are spread differently: in the picture run above, a picture
against itself scored 1, the genuinely similar one 0.37, and an unrelated
photograph 0.186. Near-duplicates score very high and everything else drops away quickly,
which is what "looks like" means and why a threshold worth using here is not the
one worth using for words.

This is why the answer states `model`: a score from `clip-vit-l14` says nothing
about a score from `dinov2-large`, and comparing them is meaningless.

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

`limit + offset` may not exceed 999. The index answers at most 1000 candidates
for one query — pgvector's own ceiling on `hnsw.ef_search` — and the last of
them is the row that tells `has_more` whether anything follows the page. A
deeper page could only be answered by guessing at that, so it is refused
instead:

```console
$ curl -s "http://127.0.0.1:8000/api/v1/search/text?q=dragon&limit=100&offset=900"
{"type":"/errors/page-too-deep","title":"Unprocessable Entity","status":422,
 "detail":"limit + offset must be at most 999, got 1000","instance":"urn:request:…"}
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

## Narrow it

A search may be narrowed to the assets that carry something — all of a set of
tags (`tags_all`), any of a set (`tags_any`), or a top-level equality in the
metadata (`meta.<key>`). The forms combine, and all four surfaces take them: the
three searches and the listing.

**A narrowing is part of the ranking, not of the page.** The answer is the
nearest assets *that satisfy it*, however deep in the ranking they sit — not
what is left after the nearest ones were fetched and then sifted. The demo
corpus tags every picture with the COCO labels it carries, so this is easy to
see:

```console
$ curl -s "http://127.0.0.1:8010/api/v1/search/text?q=a+city+street&limit=3" | jq
{"items": [
   { "tags": [], "score": 0.2 },
   { "tags": ["person","umbrella","handbag","cup","traffic-light"], "score": 0.19 },
   { "tags": [], "score": 0.177 }],
 "has_more": true, "model": "clip-vit-l14", "scan_limited": false}

$ curl -s "http://127.0.0.1:8010/api/v1/search/text?q=a+city+street&limit=3&tags_all=person" | jq
{"items": [
   { "tags": ["person","umbrella","handbag","cup","traffic-light"], "score": 0.19 },
   { "tags": ["bus","backpack","car","person","handbag"], "score": 0.17 },
   { "tags": ["bird","person","handbag"], "score": 0.16 }],
 "has_more": true, "model": "clip-vit-l14", "scan_limited": false}
```

The narrowed page is **full**, and the picture that was second without the
filter is first with it, at the same score: a narrowing decides which assets are
ranked, never how near they are.

`tags_any` is at least one of them:

```console
$ curl -s "http://127.0.0.1:8010/api/v1/search/text?q=a+city+street&limit=3&tags_any=cow,bird" | jq
{"items": [
   { "tags": ["bird","person","handbag"], "score": 0.16 },
   { "tags": ["cow"], "score": 0.155 },
   { "tags": ["cow"], "score": 0.135 }],
 "has_more": true, "scan_limited": false}
```

**`meta.<key>` is the parameter whose name you choose.** The key is matched
against `^[a-z0-9_]{1,64}$`, at most five conditions may be given, and the same
key twice is refused rather than answered with an empty page. The value is
compared for equality against the top level of the asset's metadata — so the
demo corpus, which records each picture's licence, can be searched by it:

```console
$ curl -s --get "http://127.0.0.1:8010/api/v1/search/text" \
    --data-urlencode "q=a city street" --data "limit=3" \
    --data-urlencode "meta.licence=http://creativecommons.org/licenses/by-sa/2.0/" | jq
{"items": [
   { "tags": ["cat"],      "licence": "…/licenses/by-sa/2.0/", "score": 0.131 },
   { "tags": ["boat"],     "licence": "…/licenses/by-sa/2.0/", "score": 0.119 },
   { "tags": ["elephant"], "licence": "…/licenses/by-sa/2.0/", "score": 0.103 }],
 "has_more": true, "scan_limited": false}
```

On the picture search they are form fields beside the file, `meta.<key>`
included:

```console
$ curl -s -F "file=@.data/demo/pictures/122745/000000122745.jpg" \
    -F "tags_all=person" -F "limit=3" \
    "http://127.0.0.1:8010/api/v1/search/image" | jq
{"items": [
   { "tags": ["person","umbrella","handbag","cup","traffic-light"], "score": 0.064 },
   { "tags": ["bus","backpack","car","person","handbag"], "score": 0.063 },
   { "tags": ["person"], "score": 0.05 }],
 "has_more": true, "model": "dinov2-large", "scan_limited": false}
```

And an asset may ask what looks like it **among a set it does not belong to**.
This one is tagged `cow`; narrowing its neighbours to `person` is answered, and
the asset is absent from its own answer as it always is:

```console
$ curl -s "http://127.0.0.1:8010/api/v1/assets/989f8262…/similar?limit=3" | jq
{"items": [
   { "tags": ["cow"], "score": 0.08 },
   { "tags": ["bottle","dining-table","person","knife","bowl", …], "score": 0.063 },
   { "tags": ["toilet","sink"], "score": 0.051 }],
 "has_more": true, "model": "dinov2-large", "scan_limited": false}

$ curl -s "http://127.0.0.1:8010/api/v1/assets/989f8262…/similar?limit=3&tags_all=person" | jq
{"items": [
   { "tags": ["bottle","dining-table","person","knife","bowl", …], "score": 0.063 },
   { "tags": ["person"], "score": 0.042 },
   { "tags": ["bus","backpack","car","person","handbag"], "score": 0.039 }],
 "has_more": true, "scan_limited": false}
```

The listing takes the same conditions, which is the point of them being one
thing: what you write to narrow a search you write to narrow a listing.

```console
$ curl -s --get "http://127.0.0.1:8010/api/v1/assets" --data "limit=3" \
    --data-urlencode "meta.licence=http://creativecommons.org/licenses/by-sa/2.0/" | jq
{"items": [
   { "tags": ["cat"],  "licence": "…/licenses/by-sa/2.0/" },
   { "tags": ["boat"], "licence": "…/licenses/by-sa/2.0/" },
   { "tags": ["bird"], "licence": "…/licenses/by-sa/2.0/" }],
 "has_more": true}
```

A narrowing nothing satisfies is an empty page, not an error:

```console
$ curl -s "http://127.0.0.1:8010/api/v1/search/text?q=a+city+street&tags_all=dragon" | jq
{"items": [], "has_more": false, "scan_limited": false}
```

### When a narrowed page is short

`scan_limited` is the one field a narrowed answer adds. The vector index looks
only so far; when a narrowing matches rarely, the assets that satisfy it may lie
deeper than the search was allowed to look. If that happens the answer says so:

```json
{"items": [ … ], "has_more": false, "scan_limited": true}
```

`scan_limited: true` means **this page is not the whole answer** — more matching
assets exist beyond what the search reached, whatever `has_more` says. A full
page can carry it (the row beyond the page was never reached) and so can an
empty one. Narrow the query further, ask for a smaller page, or reach the rest
through the listing, which is not ranked and has no such bound.

`scan_limited: false` means the search reached everything the answer needed: a
short page is then a short *ranking*, and a page emptied by `min_score` is the
threshold doing its job. Only a narrowed search can ever set it.

Which plan the database uses for a narrowed query is its own judgement: the
vector index, the distances of exactly the assets the narrowing admits, or — on
a corpus small enough for that to be cheapest — the distances of every vector of
the model. Only the first is bounded, so only the first can report stopping.
Where the lines fall, and what each costs, is measured in
[`benchmarks.md`](benchmarks.md).

### Refused narrowings

Every filter this service will not apply is 422 `/errors/invalid-filter`, on all
four surfaces, and the detail names the value:

```console
$ curl -s --get "http://127.0.0.1:8010/api/v1/search/text" \
    --data-urlencode "q=a city street" --data-urlencode "tags_all=not a tag!"
{"type":"/errors/invalid-filter","title":"Unprocessable Entity","status":422,
 "detail":"not a valid tag: 'not a tag!'","instance":"urn:request:…"}

$ curl -s "http://127.0.0.1:8010/api/v1/search/text?q=a+city+street&meta.Dataset=coco"
{"type":"/errors/invalid-filter","title":"Unprocessable Entity","status":422,
 "detail":"not a valid metadata key: 'Dataset'","instance":"urn:request:…"}

$ curl -s "http://127.0.0.1:8010/api/v1/search/text?q=a+city+street&meta.a=1&meta.b=2&meta.c=3&meta.d=4&meta.e=5&meta.f=6"
{"type":"/errors/invalid-filter","title":"Unprocessable Entity","status":422,
 "detail":"at most 5 metadata conditions are allowed, got 6","instance":"urn:request:…"}

$ curl -s "http://127.0.0.1:8010/api/v1/search/text?q=a+city+street&meta.dataset=coco&meta.dataset=unsplash"
{"type":"/errors/invalid-filter","title":"Unprocessable Entity","status":422,
 "detail":"metadata key given twice: 'dataset'","instance":"urn:request:…"}
```

Nothing is searched when a narrowing is refused. A tag is normalised exactly as
the tags on an asset were — ` Dragon ` and `dragon` are one tag — so a filter
matches what an upload stored.

## What is refused

| Answer | When |
|---|---|
| 422 `/errors/invalid-query` | `q` is missing, empty, only whitespace, or longer than 256 characters once trimmed — the padding is never counted against you |
| 422 `/errors/validation` | the raw `q` is longer than 1024 characters (a guard on padding, not on queries), `limit` is outside 1–100, `offset` is negative, or `min_score` is outside [−1, 1] |
| 422 `/errors/invalid-filter` | a narrowing this service will not apply: a value that is not a tag, a metadata key outside `^[a-z0-9_]{1,64}$`, more than five metadata conditions, or the same key twice |
| 422 `/errors/page-too-deep` | `limit + offset` is beyond 999 — or beyond 998 for an asset's neighbours, which spend one candidate on the asset they leave out |
| 422 `/errors/wrong-modality` | the named model cannot take that kind of query: words asked of a model with no text tower. The detail says what it *can* be asked |
| 422 `/errors/invalid-upload` | the picture search got no `file` part, or more than one, or one under another name |
| 415 `/errors/unsupported-media-type` | the bytes sent as a picture do not decode as one the service accepts — the same refusal an upload gives |
| 422 `/errors/image-too-large` · `/errors/image-too-small` | the picture is outside the bounds an upload enforces |
| 409 `/errors/not-indexed` | the asset has no vector for the search model, so it has no neighbours yet |
| 404 `/errors/not-found` | no asset carries that identifier |
| 503 `/errors/model-unavailable` | this build does not run the named model, so nothing can embed the query |

```console
$ curl -s "http://127.0.0.1:8000/api/v1/search/text?q=+"
{"type":"/errors/invalid-query","title":"Unprocessable Entity","status":422,
 "detail":"q must not be empty","instance":"urn:request:…"}

$ curl -s -X POST "http://127.0.0.1:8010/api/v1/search/image" -F "file=@notes.txt"
{"type":"/errors/unsupported-media-type","title":"Unsupported Media Type","status":415,
 "detail":"the file does not decode as an image","instance":"urn:request:…"}
```

A picture search is refused before anything is searched, and a refused picture
is gone by then: the bytes are written to a temporary file outside the media
root, inspected, and unlinked whatever happens.

## What the corpus looks like

Two views answer "what is in there" and "is indexing keeping up". Both below
are the demo corpus, after the run the picture examples came from:

```console
$ curl -s "http://127.0.0.1:8010/api/v1/tags?limit=5" | jq -c
{"items":[{"tag":"person","assets":6},{"tag":"toilet","assets":4},
          {"tag":"handbag","assets":3},{"tag":"sink","assets":3},
          {"tag":"bird","assets":2}],"limit":5}

$ curl -s http://127.0.0.1:8010/api/v1/stats | jq
{
  "assets": 20,
  "stored_bytes": 3403387,
  "work": [
    { "model": "clip-vit-l14", "status": "done", "jobs": 20 },
    { "model": "dinov2-large", "status": "done", "jobs": 21 }
  ],
  "oldest_waiting_seconds": null
}
```

One row per model per state, so two enabled models make two rows — and the
twenty-first DINOv2 job is the one `index missing` created above, which is what
that command looks like from the outside.

`stored_bytes` is the size of the originals as the assets record it —
thumbnails are not counted, and nothing walks the media root to produce it.
`oldest_waiting_seconds` is absent rather than zero when nothing is waiting.

## What this search does not do yet

- **Other languages.** CLIP ViT-L/14 was trained on English captions; other
  languages degrade towards a random ranking. The service does not translate,
  and says so rather than pretending. A picture query has no language at all,
  which is one reason to reach for it.
- **A promise about recall.** A deep page is *searched* as deeply as it asks —
  `hnsw.ef_search` is raised per query to cover the page, the row beyond it and
  any row the search must discard — but how close an approximate ranking is to
  an exact one is measured in its own change, not asserted here.
- **Which model is better at what.** This page says what each is *for*. The
  numbers — recall, latency, the cost of each — belong to the change that
  measures them.

An asset is findable as soon as it has a vector, and stays findable while a
re-index is queued: the vector it has answers until a new one replaces it. What
the queue is doing is in [`indexing.md`](indexing.md).
