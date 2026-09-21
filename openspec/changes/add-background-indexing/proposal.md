# Turn an uploaded picture into vectors

**Risk-Tier:** high

## Why

Change 4 taught the service to embed; change 5 taught it to accept a picture.
Nothing connects the two: an uploaded asset sits in the store with no vectors,
and the searches of changes 8 and 11 have nothing to search. This change is
that connection — a queue, a runner, and the endpoints that report and reset
the work.

It is also the project's first concurrency. Several runners will claim rows
from one table (the worker process of change 13 is written against the same
functions), a runner can die holding work, and delivery is at-least-once by
design, so every execution has to be safe to repeat. Those are the properties
that do not show up on a single-threaded test and hurt in production, which is
why the tier is `high` and why the verification is against a real PostgreSQL
rather than a mock.

## What Changes

- Uploading an asset enqueues one job per enabled model **in the same
  transaction as the asset**: an asset and its work are created together or
  not at all.
- A job's life: `pending` → `running` (claimed, attempt counted, lease set) →
  `done`, or back to `pending` with exponential backoff, or `failed` once the
  attempts are spent.
- Claiming uses the query the requirements fix: the rows that are pending and
  due, plus the rows whose lease has expired, `FOR UPDATE SKIP LOCKED`. Two
  claimers never take the same job, and a runner that died releases its work
  by the lease rather than by anything it has to do.
- Executing a job reads the stored original **through the same inspection an
  upload goes through** — format from the bytes, the caps again, three channels
  — because a file may have changed on disk since it was accepted (FR-IDX-7).
  It then embeds with the model the job names and writes the vector **in the
  same transaction that finishes the job**. A repeat of a delivery is harmless: the write is an upsert on
  `(asset_id, model)`.
- A stage-1 runner drains a bounded batch after the upload response, through
  the same claim/execute/finish functions the worker process will reuse.
- `index_status` joins the asset representation (a map of model key to the
  state of its newest job), the listing gains its filter, and two endpoints
  appear: the jobs of an asset, and a reset that puts selected jobs back to
  `pending` with a clean attempt count.
- A job whose asset has been deleted ends with it: the cascade takes the job
  row too, so the runner's finish matches nothing, it discards its result and
  carries on. FR-IDX-6 promised a `failed: asset-deleted` end state the schema
  cannot hold — an asset's deletion removes its jobs — and this change corrects
  the requirement to say what actually happens (Gate 1, finding 1).
- A finish only lands while the claim still owns the work. A lease alone lets
  a slow runner overwrite the state of the runner that reclaimed its job; every
  finishing statement therefore carries the token its claim handed out.
- New settings: `JOB_LEASE_SECONDS`, `JOB_MAX_ATTEMPTS`, `WORKER_BATCH_SIZE`
  (the bound both runners drain in).
- A failure's reason names the exception's class, and carries its message only
  when the service raised that exception itself; for a third-party failure the
  class alone, because nothing can tell which parts of a library's message came
  from the picture it was reading. Bounded to the two kilobytes the column
  allows. FR-IDX-3 is amended to say this, since it asked for the message
  unconditionally.
- ADR-003 records why the queue is a table in PostgreSQL rather than a broker.

## Non-goals

- The `worker` process, its graceful shutdown and the `INDEXING_RUNNER`
  switch. Change 13 owns them; this change writes the functions it will call
  and proves them under concurrency, which is the part that has to be right
  before a second process exists.
- Any search endpoint. Vectors become available here; using them is change 8
  (text) and change 11 (image).
- Priorities, fairness between assets, or a scheduler of any kind. The queue
  is first due, first served.
- Re-embedding on a model change. A new model key is a new row and a new job,
  by the schema's own rule; migrating existing assets to a new key is a
  separate concern with its own change.
- Making the API wait for indexing. Upload answers 201 as soon as the asset
  exists; the vectors arrive after.

## Capabilities

### New Capabilities

- `indexing-jobs`: the queue — what is enqueued and when, how work is claimed
  and finished, what happens to a runner that dies, and what a retry means
  when delivery is at-least-once.

### Modified Capabilities

- `asset-upload`: an asset is now its files, its row **and** its work, created
  in one transaction.
- `asset-api`: the representation gains `index_status`, the listing gains the
  filter on it, and the resource gains the jobs and reindex endpoints.

## Impact

- New: `app/services/indexing.py` (claim, execute, finish and the drain),
  `app/api/jobs.py` or the asset router's extension, `docs/adr/ADR-003-*.md`,
  a how-to section on watching the queue.
- Changed: `app/repositories/jobs.py` (the claim query and the finishing
  transitions), `app/services/assets.py` (enqueue inside the upload
  transaction, and the representation's `index_status`),
  `app/core/settings.py` (three settings), `app/schemas/assets.py`.
- Amended: FR-IDX-6 and FR-IDX-3 in `docs/explanation/requirements.md`, and the
  deletion sentence of FR-AST-12 with them, as above.
- Unchanged: the schema. Change 3 created `indexing_jobs` with the two indexes
  the claim and the status query need; no migration is written, and the claim's
  own token is the lease timestamp precisely so that none is needed.
- The first code that runs after a response has been sent, and the first that
  several processes will execute at once.
