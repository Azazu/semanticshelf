# How it is put together

The diagram in the README says who talks to whom. This says why, and what each
piece is not allowed to do. The requirements
([`requirements.md`](requirements.md)) say what the system must do; the ADRs say
why each mechanism was chosen; this page is the map between them.

## Four processes and a database

| Process | Owns | Never does |
|---|---|---|
| **API** (`app/`, uvicorn) | the HTTP contract, the media root, the queue's rows | run a model for an upload; build SQL inside a router |
| **Worker** (`semanticshelf worker`) | carrying out queued extraction | serve a request, or coordinate with another worker |
| **Interface** (`ui/`, Streamlit) | showing what the API returns | open the database, read a file, load a model, import `app` |
| **Database** (PostgreSQL 16 + pgvector) | assets, embeddings, the queue | anything the migrations did not put there |

The interface's isolation is not a convention: its image carries neither the
service nor the model runtime, and a test walks its imports to prove it never
reaches `app`.

## The request path

An upload is three writes and no inference. The bytes are read under a bound on
the whole request body, the format is decided from the bytes themselves, a
thumbnail is re-encoded from pixels, the row is written and the work is
**queued** — and the response says `pending` for each model. A picture that
never reaches a model is still stored, listed and deleted like any other, which
is what makes the queue a queue rather than a retry loop.

A search is one transaction: embed the query on the inference pool (never on the
event loop), set the index's search effort for that transaction, and run one
statement whose ordering the vector index answers. Narrowing by tags or metadata
is a condition **inside** that statement — beside the index scan rather than
over its result — because a filter applied to what the index already chose
empties the page instead of narrowing it, which change 12 measured on a corpus
of three thousand.

What a search will not do: promise a total (an exact count over an approximate
index costs a full scan and is stale when it arrives), or answer a page deeper
than the index can rank accurately (that is a 422 rather than a quietly worse
answer).

## The job path

Work is rows in `indexing_jobs`, claimed with `FOR UPDATE SKIP LOCKED` under a
lease ([ADR-003](../adr/ADR-003-queue-in-postgresql.md)). The lease is both an
expiry and a token of ownership: a completion lands only while the claim that
produced it still owns the unit, and the stored effect is an upsert on
`(asset_id, model)`. That is **at-least-once delivery with a fenced completion**
— a unit may be executed twice when a lease expires under a live runner, and one
vector is what remains. Nothing here promises exactly-once, which a lease cannot
give.

Which process carries the work out is one setting, `INDEXING_RUNNER`: the runner
inside whatever process created the work (the API after a response, an import
command after its import), or nothing but `semanticshelf worker`. The container
stack sets the second, because that is the arrangement the worker exists for.

## Storage

Three places, and each is only one:

- **The database** holds assets, embeddings and the queue. One `embeddings`
  table holds every model; the model key is part of an embedding's identity, a
  CHECK constraint carries the allowlist and each key's width, and each key has
  its own partial HNSW index over the dimension cast
  ([ADR-001](../adr/ADR-001-per-model-vector-index-layout.md),
  [ADR-002](../adr/ADR-002-vector-index-family-and-parameters.md)).
- **The media root** holds the originals and their thumbnails, under a path
  derived from the asset's identifier. Nothing a client sends reaches a path,
  and the root is never served as a directory.
- **The model cache** holds the weights, outside the image and outside the
  database, filled on first use or deliberately by `models warm`.

## What is deliberately absent

- **No broker.** The queue is a table because the database is already there,
  already transactional, and already backed up with everything else
  ([ADR-003](../adr/ADR-003-queue-in-postgresql.md)).
- **No second store.** Vectors, rows, tags and metadata are in PostgreSQL;
  adding a vector database would mean two sources of truth and one more thing to
  keep consistent.
- **No authentication.** A stated boundary of the whole project: the deployment
  shape is loopback or a private network, with a reverse proxy in front of
  anything else.
- **No GPU path.** CPU-only is a constraint, and the latencies the README quotes
  are what it costs.
- **No metrics endpoint.** `GET /api/v1/stats` answers what the interface and the
  README need; a Prometheus surface is a non-goal.

## Where the layers are enforced

Layering is checked rather than trusted, because a rule that only lives in a
document is a rule that erodes:

- routers reach neither storage nor the model layer — a router may name the
  session it is handed and nothing that builds a query;
- the model layer reaches neither the database nor the repositories;
- repositories return domain objects, never the API's own shapes, and never an
  ORM instance that would carry a session out of its transaction;
- `app/domain.py` imports no framework at all, which is what lets every other
  layer depend on it.

`tests/unit/test_layering.py` reads the import graph — including imports written
inside functions — and each of those rules has been watched to fail on a planted
violation.
