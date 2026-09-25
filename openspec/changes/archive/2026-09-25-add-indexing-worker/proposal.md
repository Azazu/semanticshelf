# Proposal — add-indexing-worker

**Risk-Tier:** high

Tier `high` for the reason AGENTS.md names outright: concurrency. This change
puts several processes on one queue at the same time, with a lease as the only
thing standing between "two runners share the work" and "two runners do the same
work twice". It also adds a signal handler — code that runs while other code is
mid-flight — and a switch that decides whether a deployment indexes anything at
all.

## Why

The queue has been a table in PostgreSQL since change 6, and every claim, lease
and retry was built for a runner that does not live inside the API process. But
the only runner that exists is the one that does: a `BackgroundTasks` callback
that takes a bounded batch after a response and stops. That is right for a demo
and wrong for everything else — indexing competes with request handling for the
same CPU and the same inference pool, a burst of uploads is worked through four
jobs at a time on the tail of whichever request happens to arrive next, and
nothing at all is indexed while the service is idle.

This change is the other half of ADR-003, and it is deliberately the *last*
piece rather than the first: the queue's mechanism was designed, tested under
concurrency and run for seven changes before the process that justifies it
arrives. What it has to prove is that the mechanism was right — the HTTP
contract does not change, no API code moves, and the same claim/execute/finish
functions run in both places.

## What Changes

- **A `worker` command.** `semanticshelf worker [--once] [--batch N]` loops:
  claim a bounded batch through the existing `claim`/`execute`/`finish`
  functions, work through it, and when nothing is due, wait a bounded moment and
  claim again. `--once` takes a single batch and exits, which is what a test and
  a cron-style deployment want.
- **Several workers on one queue, with no coordination between them.** The claim
  already passes over held rows (`FOR UPDATE SKIP LOCKED`) and a dead runner's
  work returns by lease expiry. This change proves both with real processes —
  spawned through a test-only entry point that installs the fake embedder, so no
  weights are needed — and that is the acceptance criterion the roadmap names.
  What is proven is the guarantee the queue actually gives: at-least-once
  delivery, a completion that lands only while its claim still owns the work,
  and an idempotent write. Not exactly-once, which a lease expiring under a live
  runner makes impossible and which nothing here pretends to.
- **Graceful shutdown.** On SIGTERM (and SIGINT) the worker stops claiming and
  finishes the batch it holds, then exits; nothing is released by hand, because
  a lease is what covers the work of a runner that stops (FR-CLI-2). A second
  signal exits at once, and the abandoned work returns by the same lease.
- **`INDEXING_RUNNER`**, a new setting with two values: `inline` (today's
  behaviour, and the default — a deployment that never starts a worker must keep
  indexing) and `worker` (nothing but the worker executes). It governs every
  runner that is not the worker: the upload and reindex paths in the API, and
  the two commands that finish the work they create — `index-folder` and
  `index missing`. That is not an extension of scope but the scope: FR-CLI-1
  already says `INDEXING_RUNNER` selects between the folder command's own runner
  and the worker "from change 13 onwards". The HTTP contract is identical under
  both: an upload answers `pending` and a vector arrives afterwards either way.
- **`WORKER_POLL_SECONDS`**, how long an idle worker waits before claiming
  again, bounded and documented like every other setting.
- **The documentation a person running this needs**: `docs/how-to/indexing.md`
  gains the worker — how to run it, what its log lines say, what happens on
  SIGTERM, how to run two — and `docs/reference/settings.md` plus `.env.example`
  gain both settings.

## Capabilities

### New Capabilities

None. The runner this change adds is the runner `indexing-jobs` has always
described; what is new is that it is a process of its own.

### Modified Capabilities

- `indexing-jobs`: three requirements added — the queue has a runner that is a
  process of its own, that runner stops without losing work, and which runner a
  deployment uses is configured — and one modified: the bounded-batch rule
  belongs to the runner *inside the API*, while a runner of its own is expected
  to keep going.

## Impact

- **Code**: `app/cli.py` (the command, and the two existing commands that now
  ask whether they may index), `app/services/indexing.py` (the loop, what stops
  it, and the one function that answers that question — the
  claim/execute/finish functions themselves do not change),
  `app/core/settings.py` (two settings), `app/api/assets.py` (the two places
  that schedule a drain consult the same answer; nothing else about them moves).
- **API**: no contract change. Under `INDEXING_RUNNER=worker` an upload's
  `index_status` stays `pending` until the worker gets to it, which is what it
  already says.
- **Dependencies**: none. The loop is `asyncio`, the signals are `signal`, the
  command is `typer` — all three already carry their weight in this repository.
- **Operations**: a deployment that sets `INDEXING_RUNNER=worker` and starts no
  worker never indexes. That is a real foot-gun, so it is the non-default value,
  the worker says what it is doing on every batch, and `/stats` already shows
  work that is waiting.
- **Later changes**: change 15 puts this command in Compose as its own service
  with a healthcheck; this change does not touch containers.

## Non-goals

- **No Compose service, image or healthcheck** — change 15 owns the container
  story, and a worker that runs correctly under `make run` is what it needs.
- **No LISTEN/NOTIFY.** An idle worker polls on a bounded interval. Wake-on-
  notify is a real improvement and a different mechanism (a connection held
  outside the pool, a fallback for missed notifications); it needs its own
  change and its own measurement.
- **No lease renewal.** A batch that outlives its lease is a lease set too short
  for the model, which is a setting, not a mechanism (FR-IDX-3: nothing
  refreshes a lease).
- **No parallelism inside one worker.** Concurrency comes from running several
  workers, which is what the queue was built for; a worker that ran its own
  batch in parallel would multiply the inference pool by itself.
- **No per-model or per-asset worker filters**, no prefetch, no metrics
  endpoint, no autoscaling.
- **No change to claim, lease, backoff or retry.** If this change has to alter
  them, the queue was wrong and that is a different proposal.
