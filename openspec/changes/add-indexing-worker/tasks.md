# Tasks — add-indexing-worker

Tier `high` (concurrency): Gate 1 on the artifacts, Gate 2 on the code, and **a
demonstrated failing input for every new or changed check**. Each commit that
touches the runner, the switch or the signal handling carries the
security-sensitive flag in its body, and so does `handoff.md`.

The failure this change prevents is silent in both directions: a queue nobody
drains looks exactly like a queue that is keeping up, and a runner that stops
badly looks exactly like one that stopped well until the lease expires.

## 1. The loop

- [x] 1.1 `app/services/indexing.py` gains the runner's loop, built from the
  existing `run_batch`: take a batch, and when it took nothing, wait the
  configured interval and look again (design decision 1). It reports what it did
  — batches, units, failures — as a value the caller prints, not by printing
  itself. Verify: a unit test over a fake `run_batch` asserts that a queue
  yielding two batches and then nothing is worked through in order, and that the
  loop asks again after an empty pass.
- [x] 1.2 The idle wait **is** the wait for the stop token (design decision 2):
  the loop waits on the token with the interval as its timeout, so a stop while
  idle ends it at once. Verify: a unit test with a fake clock/token asserts that
  an idle loop asked to stop returns without consuming its interval, and that an
  idle loop not asked to stop waits exactly the interval before claiming again.
  Demonstrated failing input: sleeping first and checking the token afterwards
  makes the stop take up to a full interval, which that test catches.
- [x] 1.3 One batch on request: `--once` takes at most one batch, reports, and
  returns. Verify: a unit test over the fake `run_batch` asserts exactly one
  call and no wait, on both an empty and a non-empty queue.
- [x] 1.4 `WORKER_POLL_SECONDS` in `app/core/settings.py`, bounded like its
  neighbours (`gt=0`), default 2. Verify: a unit test asserts the default, that
  the environment overrides it, and that zero and a negative value are refused
  at construction — not at the first claim.

## 2. Stopping

- [x] 2.1 The stop token and the handlers that set it: the first signal
  (`SIGTERM`, `SIGINT`) sets it and logs that a stop was asked for; the second
  restores that signal's default disposition and re-raises it at this process,
  so the runner dies the way `kill` means it to (design decision 3). Verify: a
  unit test asserts the first call sets the token and installs nothing else, and
  that the second restores the default handler and re-signals — with the signal
  module replaced, so the test never kills its own runner.
- [x] 2.2 A stop is noticed **between** batches, never inside one. Verify: an
  integration test sets the token while a batch is being worked and asserts that
  the batch's vectors are stored, that no further batch is claimed, and that the
  loop returns. Demonstrated failing input: checking the token inside the batch
  loop abandons the units already claimed, which the same test catches by their
  jobs being left `running` with no vector.
- [x] 2.3 A test-only child process that is the worker, with a rendezvous the
  parent controls (design decision 6): it installs the deterministic fake
  embedder, whose `embed_images` announces that it holds claimed work
  (`held-<pid>`) and then waits for the parent's `release`, and its stop handler
  writes `signalled-<pid>` before anything else. Verify: an integration test
  spawns it against a seeded queue, waits for `held-<pid>`, asserts the unit
  reads `running` **while the child is still inside it**, releases, and asserts
  the work finishes — the harness is worth nothing if it is not the same runner,
  and the barrier is worth nothing if the child can pass it unheld.
- [x] 2.4 A real `SIGTERM` to a runner that is demonstrably working: it finishes
  the batch it holds and exits 0. Verify: an integration test holds the child at
  the barrier, sends the signal, **waits for `signalled-<pid>`**, then releases;
  it asserts the process exits 0, that the units of that batch are `done` with
  their vectors stored, that nothing further was claimed, and that the summary
  was printed. Demonstrated failing input: a handler that cancels the running
  batch instead of setting the token leaves those units `running` with no
  vector, which this test catches.
- [x] 2.5 A second signal, delivered while the work is still held, ends the
  runner at once and leaves that work to the lease. Verify: an integration test
  holds the child at the barrier, sends `SIGTERM`, waits for the
  acknowledgement, sends `SIGTERM` again **without releasing**, and asserts the
  process ends by that signal's own disposition (not a status this project
  invented), that it printed only that it was forced, that the unit it held is
  `running` with one attempt and **not** `failed`, and that a runner claims it
  once the lease has expired — the lease shortened by settings, never by
  waiting. Demonstrated failing input: a second signal that only sets the token
  again makes the process wait for a release that never comes, which this test
  catches as a timeout.
- [x] 2.6 A stop while idle ends promptly and reports what the run did. Verify:
  an integration test spawns the child against an **empty** queue (no model is
  ever loaded, no barrier is reached), sends one signal, and asserts it exits 0
  within a few seconds having printed its summary.

## 3. Two runners on one queue

- [x] 3.1 Nothing in the claim changes; this group proves it holds between
  processes. Verify: an integration test spawns **two** child workers against
  one queue of several units, waits until **both** are held at the barrier —
  so neither the result nor the test depends on which process started first —
  releases them together, and asserts that every unit ended `done`, that the
  store holds exactly one vector per asset, that no unit counted more than one
  attempt, and that both children did some of the work.
- [x] 3.2 That a claimer does not wait for work another claimer holds is
  **already** proven deterministically, by holding a row in an open transaction
  and timing the other claim
  (`tests/integration/test_indexing.py::test_a_claimer_passes_over_work_another_holds`).
  This change adds no weaker version of it: a two-runner test cannot prove it,
  because a blocking claim would satisfy it too. Verify: that test still passes
  unchanged, and the design names it as the authority.
- [x] 3.3 A killed runner's work is covered by another. Verify: an integration
  test holds a child at the barrier, kills it (`SIGKILL`, the case no handler
  can soften — and the case where "the runner is gone, not paused" is true by
  construction), then asserts the second runner executes that work after the
  lease expires, that the unit counts two attempts — one per claim — and that
  the store still holds one vector for it.
- [ ] 3.4 A lease that expires under a runner that is still working is
  at-least-once, not a fault. Verify: an integration test shortens the lease so
  that a unit is reclaimed while its first runner is still executing, and
  asserts that the store holds one vector, that the late completion lands
  nowhere and is reported as discarded — reusing the fenced-completion tests
  change 6 already has
  (`test_a_late_success_after_a_reclaim_lands_nowhere` and its three siblings)
  as the authority for the mechanism rather than restating it.

## 4. Which runner the deployment uses

- [ ] 4.1 `INDEXING_RUNNER` in `app/core/settings.py`: `inline` (default) or
  `worker`, refused otherwise at construction. Verify: unit tests for the
  default, for both values from the environment, and for a third value being
  refused with the name in the message.
- [ ] 4.2 One place decides whether a request schedules a drain (design decision
  4), and both routers call it — upload and reindex. Verify: a unit test asserts
  the decision for both settings values; an api test asserts that under `worker`
  an upload answers exactly as it does under `inline` (same status, same body
  shape, `index_status` `pending`) while nothing is scheduled, and that under
  `inline` it still is. Demonstrated failing input: leaving one of the two call
  sites comparing the setting itself makes the reindex path index under
  `worker`, which the api test for that path catches.
- [ ] 4.3 The HTTP contract is identical under both. Verify: an integration test
  uploads under `INDEXING_RUNNER=worker`, asserts the work is queued and no
  vector appears without a runner, then runs one `--once` batch and asserts the
  vector is there and the asset reads `done`.
- [ ] 4.4 The commands that finish the work they create consult the same
  decision (design decision 4, FR-CLI-1): `index-folder` and `index missing`
  import or queue as they do now and execute nothing under
  `INDEXING_RUNNER=worker`. Verify: unit tests over each command's runtime
  assert that the work-finishing step is not reached under `worker` and is under
  `inline`; an integration test runs `index-folder` on a fixture tree under
  `worker` and asserts the assets exist with their work `pending` and no
  vectors, then runs the worker once and asserts they finish. Demonstrated
  failing input: leaving `index-folder` on its own `index=not no_index` makes
  the first of those tests find vectors that should not exist yet.
- [ ] 4.5 `--no-index` and the switch say the same thing from two directions and
  never contradict each other. Verify: unit tests assert the summary under
  `--no-index`, under `worker`, and under both at once report the work as queued
  and name which of the two decided it — and that no combination reports work as
  indexed that was not.

## 5. The command

- [x] 5.1 `semanticshelf worker [--once] [--batch N]` in `app/cli.py`: builds the
  engine, session factory, storage and inference pool, installs the handlers,
  runs the loop, and disposes both in a `finally` — the shape `index missing`
  already has. `--batch` overrides `WORKER_BATCH_SIZE` for this process only.
  Verify: a unit test asserts the command's options and that `--batch 0` is
  refused; the integration test of 2.4 covers the real process.
- [x] 5.2 What it says: one line when it starts (batch size, interval, which
  models are enabled), one per batch that did something, one when it ends
  gracefully with the totals, and — when it is forced — one line saying so and
  nothing else (the spec's report guarantee belongs to the graceful path).
  Verify: the spawned-process tests of 2.4 and 2.6 assert the start line, the
  summary on a graceful end and its absence on a forced one; a unit test asserts
  a batch that took nothing logs nothing.

## 6. Documentation

- [ ] 6.1 `docs/how-to/indexing.md` gains the worker: how to run it, what
  `INDEXING_RUNNER` does, what happens on SIGTERM, how to run two, and what to
  look at when nothing is being indexed (`/stats`, `index_status`). Verify:
  every command in the page was run in the form shown, against a real service
  and a real worker.
- [ ] 6.2 `docs/reference/settings.md` and `.env.example` gain
  `INDEXING_RUNNER` and `WORKER_POLL_SECONDS`, with the same columns every other
  setting has (who reads it, default, what it means). Verify: the page lists
  both; `rg` finds no setting in `Settings` that the page or the template omits.
- [ ] 6.3 `docs/explanation/requirements.md` reads as the service behaves:
  FR-IDX-2 and FR-CLI-2 name the command as it actually is (`semanticshelf
  worker`, not `python -m app.cli worker`); FR-IDX-2 says what `INDEXING_RUNNER`
  decides and states the guarantee as at-least-once with a fenced completion
  rather than as exactly-once; and **FR-CLI-1's promise is kept** — its sentence
  "`INDEXING_RUNNER` selects between this runner and the worker process from
  change 13 onwards" now describes something that exists, with `--no-index`'s
  relation to it stated. Verify: `openspec validate --all --strict` passes,
  `rg 'INDEXING_RUNNER' docs/` finds no statement the code does not make, and
  every command named in those requirements exists with that spelling.
- [ ] 6.4 `openspec/ROADMAP.md` row 13 says what this change did. Verify: the
  row names the command, the switch and the evidence.

## 7. Evidence

- [ ] 7.1 `make check`, `make test-integration` and `make test-ui` green the way
  CI runs them (`FORCE_COLOR=1 CI=true`), `openspec validate --all --strict`,
  every `scripts/*_test.sh`, and `sh -n` over `scripts/*.sh`.
- [ ] 7.2 A real run captured into the how-to: a service with
  `INDEXING_RUNNER=worker`, an upload that stays `pending`, a worker started,
  the vector arriving, and the worker stopped with a signal.
