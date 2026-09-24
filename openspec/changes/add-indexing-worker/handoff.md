# Handoff — add-indexing-worker

**Updated:** 2026-09-24 · claude
**State:** fixing-g1
**Branch:** change/add-indexing-worker

## Done this session

Branch, scaffold and all four planning artifacts.

The change is deliberately small in code and large in evidence: the loop is
three lines of policy around `run_batch`, and everything that matters is what
happens around it — a stop that finishes the batch it holds, a second signal
that hands the process back to the operating system, two runners that never take
the same unit, and a switch that decides which runner a deployment has. Nothing
about claim, lease, backoff or retry changes; if it had to, the queue would have
been wrong since change 6.

Two decisions worth knowing before reading the design:

- **The idle wait is the wait for the stop token.** The loop waits on the token
  with the poll interval as its timeout, so "asked to stop while idle" ends at
  once and "asked to stop while working" is noticed between batches — which is
  what finishing the batch you hold means mechanically.
- **Evidence is split by what each kind can prove.** Two loops against one real
  database prove the shared queue; a real `semanticshelf worker` process sent a
  real `SIGTERM` proves the stop — over an **empty** queue, so no weights are
  loaded and CI stays honest.

## Next step

`/gate-review add-indexing-worker 1 confirm 1` again — confirmation 1 confirmed
finding 2 and sent findings 1 and 3 back, both fairly:

- **1** — the general guarantee was fixed, but the old scenario still promised
  that work from a "stopped" runner is "never executed twice at the same time".
  A paused runner is not a gone runner. The scenario now says *terminated*, and
  makes no claim at all about a slow or paused one: what protects the store
  there is the fenced completion and the idempotent write, which the requirement
  states.
- **3** — the processes were real but not held still. Observing that a unit
  reads `running` says the child claimed it, not that it is still there when the
  signal lands; and two signals with no acknowledgement between them can
  coalesce or arrive after a graceful exit. The harness now carries a barrier
  inside the fake embedder (`held-<pid>` → wait for `release`) and an
  acknowledgement in the stop handler (`signalled-<pid>`), and every process
  test rendezvouses through them: both children are held before either is
  released, the second signal is delivered while the work is still held, and
  every wait is bounded and fails naming what it waited for.

Finding 4 was not disputed. 27 tasks; `scripts/pregate-verify.sh gate1
add-indexing-worker` passes.

## Blockers

None.
