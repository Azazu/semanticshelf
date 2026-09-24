# Design — add-indexing-worker

## Context

See `proposal.md` — Why. What this design has to work with, all of it already
in the repository:

- **The three steps exist and are proven.** `claim` (one transaction,
  `FOR UPDATE SKIP LOCKED`, an attempt counted and a lease set), `execute` (no
  connection held while the model runs) and `finish` (the vector and the
  `done` mark in one transaction, conditional on still owning the lease) live in
  `app/services/indexing.py` and are exercised under concurrency by change 6's
  integration suite. `run_batch` already composes them. **This change adds no
  step and changes none.**
- **A lease is the only thing that returns work.** Nothing refreshes it
  (`JOB_LEASE_SECONDS`, 600 by default); a runner that stops holding work
  releases it by expiry, and the claim treats `running AND lease_expires_at <
  now()` as due. That is the mechanism behind every guarantee below about
  stopping.
- **The in-request runner is bounded on purpose.** `drain` takes at most
  `WORKER_BATCH_SIZE` jobs after a response and stops, because it shares a
  process with the requests. The new runner does not share that process, which
  is the whole difference between them.
- **A CLI command that owns a runtime has a shape here already.**
  `semanticshelf index missing` builds the engine, the session factory, the
  storage and the inference pool, runs an async function, and disposes both in a
  `finally` (`app/cli.py::_run_backfill`). The worker is the same shape with a
  different body.
- **`asyncio` signal handling is the loop's, not the library's.**
  `asyncio.AbstractEventLoop.add_signal_handler` exists on this platform and is
  what lets a signal set a flag the loop is already waiting on, rather than
  interrupting arbitrary code.

## Goals / Non-Goals

**Goals:**

- A runner that is a process of its own, built from the steps that already
  exist, so that what is proven about them stays proven.
- A stop that is honest: finish the batch, take nothing new, end — and leave
  anything unfinished to the lease rather than inventing a release path.
- One place that decides which runner a deployment uses, consulted by both
  places that schedule work today.
- Evidence with processes and signals, not only with tasks and flags.

**Non-Goals:** everything in the proposal's Non-goals, and in particular no
change to claim, lease, backoff or retry — if this change needed one, the queue
would have been wrong for seven changes.

## Decisions

1. **The loop lives in the service layer; the command is an adapter.**
   `app/services/indexing.py` gains the loop and the token that stops it;
   `app/cli.py` builds the runtime, installs the signal handlers and calls it.
   Same division as `index-folder` and `index missing`, and it is what lets the
   loop be tested without a subprocess — the CLI adds no behaviour of its own.

   Rejected: putting the loop in the CLI (untestable without spawning), and a
   new module for it (the loop is three lines of policy around `run_batch`; its
   neighbours are the functions it calls).

2. **What stops the loop is an object it waits on, not a flag it polls.** The
   loop's idle wait *is* the wait for that token: it waits for the stop token
   with the poll interval as a timeout. Asked to stop while idle, the wait ends
   at once and the runner exits — which is the spec's "ends promptly, without
   waiting out its interval". Asked to stop while working, the token is set and
   the loop notices it where it always looks: **between batches**, which is what
   "finish the batch you hold" means mechanically.

   Rejected: cancelling the task that runs the batch (that is abandoning work
   mid-flight — the opposite of the requirement), and checking the token inside
   `run_batch` (the batch is where the model runs; a stop that interrupts it
   would leave a claim held with nothing to show and buy nothing over the lease).

3. **The second signal is the operating system's business.** The first signal
   sets the token. The second restores the default disposition for that signal
   and re-raises it at this process, so the runner dies the way `kill` means it
   to, with the status a supervisor expects — rather than with an exit code this
   project invented. Work in flight then returns by its lease, like a crash,
   because from the queue's point of view that is exactly what it is.

4. **`INDEXING_RUNNER` is read in one place.** A function in the service layer
   decides whether an HTTP request schedules a drain, and both routers call it
   instead of comparing the setting themselves. The switch is one fact about the
   deployment, and a fact stated twice drifts. `inline` is the default: a build
   nobody configured must still index what it accepts, and the demo depends on
   it.

5. **The worker is one process, one batch at a time.** Concurrency is other
   workers, not threads inside this one: the inference pool is already bounded
   per process (`INFERENCE_WORKERS`), and running a batch in parallel inside one
   worker would multiply it by the batch size. A deployment that wants more
   throughput starts more workers, which the queue has always supported.

6. **Two kinds of evidence, because a signal and a shared queue are different
   claims.**
   - *Shared queue*: two loops against one real database, running as tasks in
     one test, over a queue of several units — every unit executed exactly once,
     none by both, neither loop waiting for the other. Tasks are enough here
     because `SKIP LOCKED` works at the transaction level, and the test asserts
     what the queue says afterwards, not what the runners felt.
   - *Signal*: a real `semanticshelf worker` process, sent a real `SIGTERM`.
     That test runs against an **empty queue**, so no model is ever loaded and
     no weights are needed — it proves the thing only a process can prove (the
     signal arrives, the runner ends promptly, the exit is clean). Stopping
     *while holding a batch* is proven in-process instead, by setting the token
     mid-batch and asserting that the batch finished and nothing new was taken.

   Rejected: a subprocess test that indexes something (it would need real
   weights in CI, which this project never does), and proving the signal with a
   fake (a fake signal proves the handler was called, not that the process
   stops).

7. **The idle interval is a setting with a small default.** `WORKER_POLL_SECONDS`
   (default 2). It trades latency for idle queries against an indexed claim; a
   deployment that wants neither can run `--once` on a schedule. Named and
   documented like every other setting, including in `.env.example` and
   `docs/reference/settings.md`, because a setting that only the code knows
   about is a setting nobody sets.

## Applicability

| Question | Answer |
|---|---|
| Crash before/after an external effect | The external effect is the vector. `finish` writes it and marks the job done in one transaction, conditional on the lease still being ours (change 6), so a crash before it leaves the work claimed — returned by lease — and a crash after it leaves the work done. A stop is a crash the queue already knows how to survive; this change adds no new window, and the loop does nothing between `execute` and `finish` that could. |
| Concurrent writers | Several runners on one queue is the point. The mechanism is the existing claim: `FOR UPDATE SKIP LOCKED` under one transaction, an attempt counted and a lease set at claim time, and every finish conditional on that lease. What it does NOT guarantee: exactly-once execution. Delivery is at-least-once — a lease that expires while its runner is alive is claimed by another, and both may compute the same vector. The upsert on `(asset_id, model)` is what makes that harmless. |
| Empty / zero / null inputs | An empty queue is the normal state: the runner waits its interval and looks again, and `--once` on an empty queue reports nothing taken and exits 0. A batch size or poll interval of zero or less is refused by the settings' own bounds, at startup, not at the first claim. |
| Deletion / expiry | Two expiries meet here. A lease that expires makes work claimable again and counts a new attempt (existing). An asset deleted while its work is in flight takes the job row with it, so the finish matches nothing and the result is discarded without a retry (FR-IDX-6, existing). The worker inherits both; what it adds is that a stopped runner leans on the first deliberately. |
| Idempotency of retries | Unchanged and depended upon: the embedding write is an upsert on `(asset_id, model)`, so a unit executed twice leaves one row. The worker makes repeats more likely (more runners, more leases), which is why this row is not `n/a`. |
| Money rounding · Authorization boundary | n/a — this change touches neither. |

## Risks / Trade-offs

- **A deployment set to `worker` with no worker running never indexes.** The
  foot-gun is real and cannot be designed away by the runner. Mitigations: it is
  not the default; the setting is documented in two places; `/stats` already
  reports work that is waiting and how old the oldest is; and `index_status`
  says `pending` on every asset, which is the first thing a person looks at.
  What this design will NOT do is have the API notice and index anyway — a
  fallback would make the switch meaningless and put the work back where the
  change removed it from.
- **The poll interval is a floor on latency.** At two seconds, an upload's
  vector is up to two seconds later than under the in-request runner (plus the
  model). That is the trade a queue with no notification makes; LISTEN/NOTIFY is
  named as a non-goal rather than pretended away.
- **A long batch outlives a short lease.** Four jobs of a slow model on a cold
  process can exceed a lease set low by a deployment, and then another runner
  claims work this one is still doing. The result is wasted CPU, not corruption
  (the upsert and the lease check cover it), and the existing guidance —
  `JOB_LEASE_SECONDS` is raised for a slow model — is where this belongs.
- **Two runners at once (inline API and a worker) is legal.** Nothing forbids
  running a worker while the API is still `inline`; the claim keeps them apart.
  It is not recommended, because the API then competes for its own CPU, and the
  documentation says so rather than the code refusing it.
- **The signal test spawns a process.** It is slower than the rest of the suite
  and depends on the platform's signal semantics. It is worth it: everything
  else about the stop is a claim about what a process does when the operating
  system asks it to end, and no in-process test can make that claim.

## Migration Plan

Nothing to migrate: no schema change, no data change, no API change. A
deployment that does nothing keeps the runner it has. Turning the worker on is
setting `INDEXING_RUNNER=worker` and starting `semanticshelf worker`; turning it
off is the reverse, and work queued meanwhile is picked up by whichever runner
is next to claim.

## Open Questions

None. The one question this change could have asked — whether the API should
fall back to indexing when no worker has claimed for a while — is answered in
Risks: it should not, and a deployment that wants that behaviour keeps `inline`.
