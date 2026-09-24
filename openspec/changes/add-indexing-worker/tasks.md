# Tasks — add-indexing-worker

Tier `high` (concurrency): Gate 1 on the artifacts, Gate 2 on the code, and **a
demonstrated failing input for every new or changed check**. Each commit that
touches the runner, the switch or the signal handling carries the
security-sensitive flag in its body, and so does `handoff.md`.

The failure this change prevents is silent in both directions: a queue nobody
drains looks exactly like a queue that is keeping up, and a runner that stops
badly looks exactly like one that stopped well until the lease expires.

## 1. The loop

- [ ] 1.1 `app/services/indexing.py` gains the runner's loop, built from the
  existing `run_batch`: take a batch, and when it took nothing, wait the
  configured interval and look again (design decision 1). It reports what it did
  — batches, units, failures — as a value the caller prints, not by printing
  itself. Verify: a unit test over a fake `run_batch` asserts that a queue
  yielding two batches and then nothing is worked through in order, and that the
  loop asks again after an empty pass.
- [ ] 1.2 The idle wait **is** the wait for the stop token (design decision 2):
  the loop waits on the token with the interval as its timeout, so a stop while
  idle ends it at once. Verify: a unit test with a fake clock/token asserts that
  an idle loop asked to stop returns without consuming its interval, and that an
  idle loop not asked to stop waits exactly the interval before claiming again.
  Demonstrated failing input: sleeping first and checking the token afterwards
  makes the stop take up to a full interval, which that test catches.
- [ ] 1.3 One batch on request: `--once` takes at most one batch, reports, and
  returns. Verify: a unit test over the fake `run_batch` asserts exactly one
  call and no wait, on both an empty and a non-empty queue.
- [ ] 1.4 `WORKER_POLL_SECONDS` in `app/core/settings.py`, bounded like its
  neighbours (`gt=0`), default 2. Verify: a unit test asserts the default, that
  the environment overrides it, and that zero and a negative value are refused
  at construction — not at the first claim.

## 2. Stopping

- [ ] 2.1 The stop token and the handlers that set it: the first signal
  (`SIGTERM`, `SIGINT`) sets it and logs that a stop was asked for; the second
  restores that signal's default disposition and re-raises it at this process,
  so the runner dies the way `kill` means it to (design decision 3). Verify: a
  unit test asserts the first call sets the token and installs nothing else, and
  that the second restores the default handler and re-signals — with the signal
  module replaced, so the test never kills its own runner.
- [ ] 2.2 A stop is noticed **between** batches, never inside one. Verify: an
  integration test sets the token while a batch is being worked and asserts that
  the batch's vectors are stored, that no further batch is claimed, and that the
  loop returns. Demonstrated failing input: checking the token inside the batch
  loop abandons the units already claimed, which the same test catches by their
  jobs being left `running` with no vector.
- [ ] 2.3 What a stopped runner leaves behind is claimable, not failed. Verify:
  an integration test stops a runner that holds work it cannot finish (the
  second signal path), then asserts the job is `running` with its attempt
  counted, is not `failed`, and is claimed by another runner once the lease has
  expired — with the lease shortened by settings rather than by waiting.
- [ ] 2.4 A real process, a real signal: the published command run against an
  **empty** queue, sent `SIGTERM`, ends promptly and cleanly (design decision 6).
  Verify: an integration test spawns `uv run semanticshelf worker`, waits for the
  line that says it started, sends the signal, and asserts the process exits 0
  within a few seconds and printed what it did. No model is loaded, because
  nothing is due.

## 3. Two runners on one queue

- [ ] 3.1 Nothing in the claim changes; this group only proves it holds for the
  loop. Verify: an integration test runs two loops concurrently against one
  queue of several units and asserts every unit ended `done` exactly once, that
  the number of vectors equals the number of assets, and that no unit counted
  more than one attempt.
- [ ] 3.2 Neither runner waits for the other. Verify: the same test asserts both
  loops took work (neither ended up with zero), which is what `SKIP LOCKED`
  buys and what a lock-waiting claim would lose.
- [ ] 3.3 A runner that stopped mid-flight is covered by another. Verify: an
  integration test claims work in one loop, stops it hard, and asserts the
  second loop executes that work exactly once after the lease expires — the
  attempt counter showing two attempts, one per claim.

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

## 5. The command

- [ ] 5.1 `semanticshelf worker [--once] [--batch N]` in `app/cli.py`: builds the
  engine, session factory, storage and inference pool, installs the handlers,
  runs the loop, and disposes both in a `finally` — the shape `index missing`
  already has. `--batch` overrides `WORKER_BATCH_SIZE` for this process only.
  Verify: a unit test asserts the command's options and that `--batch 0` is
  refused; the integration test of 2.4 covers the real process.
- [ ] 5.2 What it says: one line when it starts (batch size, interval, which
  models are enabled), one per batch that did something, one when it ends with
  the totals. Verify: the spawned-process test asserts the start line and the
  end line; a unit test asserts a batch that took nothing logs nothing.

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
  worker`, not `python -m app.cli worker`), and FR-IDX-2 says what
  `INDEXING_RUNNER` decides. Verify: `openspec validate --all --strict` passes
  and the text matches the code.
- [ ] 6.4 `openspec/ROADMAP.md` row 13 says what this change did. Verify: the
  row names the command, the switch and the evidence.

## 7. Evidence

- [ ] 7.1 `make check`, `make test-integration` and `make test-ui` green the way
  CI runs them (`FORCE_COLOR=1 CI=true`), `openspec validate --all --strict`,
  every `scripts/*_test.sh`, and `sh -n` over `scripts/*.sh`.
- [ ] 7.2 A real run captured into the how-to: a service with
  `INDEXING_RUNNER=worker`, an upload that stays `pending`, a worker started,
  the vector arriving, and the worker stopped with a signal.
