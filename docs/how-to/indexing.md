# Watch, and rerun, the indexing of a picture

An upload answers as soon as the asset exists; its vectors arrive after.
This is how to see where that work has got to, what it says when it fails,
and how to make it run again.

Every command here was run in the form shown against a local service on a
migrated database, with `MEDIA_ROOT=.data/media` and — so that one failure is
final rather than retried three times — `JOB_MAX_ATTEMPTS=1`. The answers are
the answers it gave; identifiers are shortened in the commands and differ from
run to run.

## The four states

| State | What it means |
|---|---|
| `pending` | queued, waiting for a runner. A job that failed with attempts left is `pending` again, due after its backoff |
| `running` | a runner holds it. The claim carries a lease (`JOB_LEASE_SECONDS`, ten minutes by default); a runner that dies leaves the job claimable again once that expires |
| `done` | the vector is stored. The job and the vector are written in one transaction, so one never exists without the other |
| `failed` | the attempts are spent. Nothing claims it again — a reset is the only way it runs once more |

There is one job per asset per enabled model, and `index_status` reports the
newest job of each model.

## Where the work has got to

The upload's own answer already carries it:

```console
$ curl -s -X POST http://127.0.0.1:8000/api/v1/assets \
    -F "file=@dragon.png" -F "tags=dragon,blue"
{
    "id": "56a8ec8b-6b45-4b6c-9679-179ac06e4984",
    …
    "index_status": {"clip-vit-l14": "pending"}
}
```

A moment later it is done — in the background, and the first one also loads
the model:

```console
$ curl -s http://127.0.0.1:8000/api/v1/assets/56a8ec8b-… | jq .index_status
{
  "clip-vit-l14": "done"
}
```

The detail is one call further:

```console
$ curl -s http://127.0.0.1:8000/api/v1/assets/56a8ec8b-…/jobs | jq '.items[0]'
{
  "id": "072d61a7-e315-4d04-853d-6dc83d302056",
  "model": "clip-vit-l14",
  "status": "done",
  "attempts": 1,
  "available_at": "2026-09-21T14:24:26.505414Z",
  "lease_expires_at": null,
  "last_error": null,
  "created_at": "2026-09-21T14:24:26.505414Z",
  "started_at": "2026-09-21T14:24:26.561947Z",
  "finished_at": "2026-09-21T14:24:29.409125Z"
}
```

`started_at` and `finished_at` are of the **latest** attempt; `attempts`
counts every claim, including the ones a lease expiry handed back.
`lease_expires_at` is null here because the job holds no claim any more — while
one is `running` it says when that claim stops being the owner, which is the
moment another runner may take the job.

## Find the work that needs attention

The listing filters on the state of one model's newest job,
`index_status=<model>:<state>`:

```console
$ curl -s "http://127.0.0.1:8000/api/v1/assets?index_status=clip-vit-l14:failed" \
    | jq '{items: [.items[] | {id, tags, index_status}], limit, offset, has_more}'
{
  "items": [
    {
      "id": "56a8ec8b-6b45-4b6c-9679-179ac06e4984",
      "tags": [
        "dragon",
        "blue"
      ],
      "index_status": {
        "clip-vit-l14": "failed"
      }
    }
  ],
  "limit": 20,
  "offset": 0,
  "has_more": false
}
```

It combines with the other filters (`tags_all`, `tags_any`, `source`) and is
refused when it names something the service does not know:

```console
$ curl -s "http://127.0.0.1:8000/api/v1/assets?index_status=clip-vit-l14:finished"
{"type":"/errors/invalid-filter","title":"Unprocessable Entity","status":422,
 "detail":"unknown state: 'finished'; expected one of pending, running, done, failed",
 "instance":"urn:request:…"}

$ curl -s "http://127.0.0.1:8000/api/v1/assets?index_status=dinov2-xl:done"
{"type":"/errors/invalid-filter","title":"Unprocessable Entity","status":422,
 "detail":"unknown model: 'dinov2-xl'","instance":"urn:request:…"}
```

An asset that has no work for the named model matches no state at all: there
is nothing to be in one.

## When it fails

A stored original is inspected again before it is decoded, because the file on
disk is not necessarily the file that was accepted. Here it was replaced with
something that is not a picture:

```console
$ printf 'this is not a picture any more' > .data/media/56/56a8ec8b-….png
$ curl -s -X POST http://127.0.0.1:8000/api/v1/assets/56a8ec8b-…/reindex \
    -H 'content-type: application/json' -d '{"models": ["clip-vit-l14"]}'
{"asset_id":"56a8ec8b-6b45-4b6c-9679-179ac06e4984","models":["clip-vit-l14"],"jobs":1}

$ curl -s http://127.0.0.1:8000/api/v1/assets/56a8ec8b-…/jobs | jq '.items[0]'
{
  "id": "072d61a7-e315-4d04-853d-6dc83d302056",
  "model": "clip-vit-l14",
  "status": "failed",
  "attempts": 1,
  "available_at": "2026-09-21T14:24:37.723700Z",
  "lease_expires_at": null,
  "last_error": "StoredFileUnusable: UndecodableImageError: the file does not decode as an image",
  "created_at": "2026-09-21T14:24:26.505414Z",
  "started_at": "2026-09-21T14:24:37.737025Z",
  "finished_at": "2026-09-21T14:24:37.742599Z"
}
```

`last_error` names the failure's class, and carries a message only when the
service raised that failure itself — a library's message may hold bytes it
read out of the file, and nothing can tell which parts. It is bounded to two
kilobytes with any truncation visible, and never holds a stack trace.

With the default `JOB_MAX_ATTEMPTS=3` this job would have gone back to
`pending` twice first, due again after 20 s and then 40 s
(`2^attempts × 10 s`).

## Run it again

`reindex` puts the work back in the queue with its attempts and its reason
cleared. It is the only way failed work runs again — nothing retries a job
that reached `failed` on its own.

```console
$ cp dragon.png .data/media/56/56a8ec8b-….png          # a picture again
$ curl -s -X POST http://127.0.0.1:8000/api/v1/assets/56a8ec8b-…/reindex
{"asset_id":"56a8ec8b-6b45-4b6c-9679-179ac06e4984","models":["clip-vit-l14"],"jobs":1}

$ curl -s http://127.0.0.1:8000/api/v1/assets/56a8ec8b-…/jobs | jq '.items[0]'
{
  "id": "072d61a7-e315-4d04-853d-6dc83d302056",
  "model": "clip-vit-l14",
  "status": "running",
  "attempts": 1,
  "available_at": "2026-09-21T14:24:44.437156Z",
  "lease_expires_at": "2026-09-21T14:34:44.442848Z",
  "last_error": null,
  "created_at": "2026-09-21T14:24:26.505414Z",
  "started_at": "2026-09-21T14:24:44.442848Z",
  "finished_at": null
}
```

That one caught the runner at work — the answer to a reset comes back before
the work is done, which is the whole point. Immediately after:

```console
$ curl -s http://127.0.0.1:8000/api/v1/assets/56a8ec8b-…/jobs | jq '.items[0]'
{
  "id": "072d61a7-e315-4d04-853d-6dc83d302056",
  "model": "clip-vit-l14",
  "status": "done",
  "attempts": 1,
  "available_at": "2026-09-21T14:24:44.437156Z",
  "lease_expires_at": null,
  "last_error": null,
  "created_at": "2026-09-21T14:24:26.505414Z",
  "started_at": "2026-09-21T14:24:44.442848Z",
  "finished_at": "2026-09-21T14:24:44.846850Z"
}
```

With no body — or with `"models": null` — the reset takes every model's work;
`{"models": [...]}` selects. An empty list is a selection of nothing and
resets nothing, so a caller that builds its list by filtering does not lose
everything when the filter matches none of it:

```console
$ curl -s -X POST http://127.0.0.1:8000/api/v1/assets/56a8ec8b-…/reindex \
    -H 'content-type: application/json' -d '{"models": []}'
{"asset_id":"56a8ec8b-6b45-4b6c-9679-179ac06e4984","models":[],"jobs":0}
```

The answer reports what was actually reset, which is not always what was asked
for — an asset that never had work for a model has none to put back:

```console
$ curl -s -X POST http://127.0.0.1:8000/api/v1/assets/56a8ec8b-…/reindex \
    -H 'content-type: application/json' -d '{"models": ["dinov2-large"]}'
{"asset_id":"56a8ec8b-6b45-4b6c-9679-179ac06e4984","models":[],"jobs":0}
```

Both endpoints answer 404 for an identifier no asset carries, and `reindex`
answers 422 for a model the service does not know:

```console
$ curl -s http://127.0.0.1:8000/api/v1/assets/0f9b1d2c-3e4f-4a5b-8c7d-9e0f1a2b3c4d/jobs
{"type":"about:blank","title":"Not Found","status":404,
 "detail":"no such asset","instance":"urn:request:…"}

$ curl -s -X POST http://127.0.0.1:8000/api/v1/assets/56a8ec8b-…/reindex \
    -H 'content-type: application/json' -d '{"models": ["dinov2-xl"]}'
{"type":"/errors/unknown-model","title":"Unprocessable Entity","status":422,
 "detail":"unknown model: 'dinov2-xl'","instance":"urn:request:…"}
```

## Who actually does the work

In this stage, the API process: every upload — and every reset — schedules a
background task that claims at most `WORKER_BATCH_SIZE` jobs, does them, and
stops. A runner that drained while work remained would never end, so anything
left over waits for the next upload or reset. The separate `worker` process,
which loops over the same claim, execute and finish functions, arrives with
its own change.

Two consequences worth knowing:

- Work can be claimed twice if it outlives its lease — a slow model, a
  suspended process. It is harmless: the vector write replaces the row for
  that asset and model, and only the runner that still holds the claim can
  finish the job; the one that lost it discards its result.
- Deleting an asset takes its work with it. A runner holding that work finds
  its finish matching nothing, discards the result and carries on.

Why the queue is a table in PostgreSQL rather than a broker, and what the
lease buys, is [ADR-003](../adr/ADR-003-queue-in-postgresql.md).

## The settings that shape it

| Setting | Default | What it does |
|---|---|---|
| `JOB_LEASE_SECONDS` | 600 | how long a claim is good for; after it, another runner may take the job |
| `JOB_MAX_ATTEMPTS` | 3 | how many attempts a job gets before it is `failed` for good |
| `WORKER_BATCH_SIZE` | 4 | how many jobs one run of a runner takes |

They sit with every other setting in
[`../reference/settings.md`](../reference/settings.md).
