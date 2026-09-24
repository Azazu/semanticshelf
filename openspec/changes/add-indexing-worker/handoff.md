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

`/gate-review add-indexing-worker 1 confirm 1` — Gate 1 round 1 asked for
changes (three major, one minor) and all four are addressed:

1. The spec promised **exactly-once**; the queue gives at-least-once with a
   fenced completion and an idempotent write. The requirement now says that in
   those words, the two-runner scenario carries its preconditions, and a new
   scenario covers a lease expiring under a runner that is still working.
2. FR-CLI-1 already promises that `INDEXING_RUNNER` selects between the folder
   command's own runner and this worker. The switch now governs every runner
   that is not the worker — the two API paths **and** `index-folder` and
   `index missing` — with `--no-index`'s relation to it stated, tasks for both,
   and FR-CLI-1 named in the documentation task.
3. The evidence is processes, as the proposal claimed: a test-only child entry
   point installs the fake embedder and runs what the command runs, so two real
   workers share one queue and a real `SIGTERM` reaches a runner that is working
   — no weights, still in the integration suite. Task 3.2 no longer pretends a
   two-runner test proves the absence of lock waits; change 6's held-transaction
   test is named as the authority.
4. A forced end reports only that it was forced; the summary is the graceful
   path's guarantee, in the spec and in the design.

27 tasks now (was 22). `scripts/pregate-verify.sh gate1 add-indexing-worker`
passes.

## Blockers

None.
