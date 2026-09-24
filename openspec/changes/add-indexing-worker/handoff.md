# Handoff — add-indexing-worker

**Updated:** 2026-09-24 · claude
**State:** awaiting-gate-1
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

`/gate-review add-indexing-worker 1` — tier `high` (concurrency), so Gate 1 runs
on the artifacts before any code. `scripts/pregate-verify.sh gate1
add-indexing-worker` passes (22 tasks, applicability table present, links
resolve).

After the gate: `/opsx:apply add-indexing-worker`.

## Blockers

None.
