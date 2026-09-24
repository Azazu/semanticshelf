# Handoff — add-indexing-worker

**Updated:** 2026-09-24 · claude
**State:** implementing
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

`/opsx:apply add-indexing-worker` — **Gate 1 passed** (confirmation 2 of round
1, commit `c204c6c`): all three remaining findings confirmed, nothing new added.

27 tasks, in the order the groups are written:

- **1.x** the loop, the idle wait that is the wait for the stop token, `--once`,
  `WORKER_POLL_SECONDS`.
- **2.x** stopping: the token and its handlers, a stop noticed between batches,
  and the child harness with its barrier (`held-<pid>` → `release`) and its
  acknowledgement (`signalled-<pid>`) — every process test rendezvouses through
  them.
- **3.x** two runners on one queue, a killed one covered by the other, and a
  lease expiring under a runner that is still working; change 6's
  held-transaction test stays the authority for no-lock-waiting.
- **4.x** `INDEXING_RUNNER`, one function that answers "may this process index
  itself?", and the four callers: upload, reindex, `index-folder`,
  `index missing`.
- **5.x** the command and what it says.
- **6.x / 7.x** the documentation — including FR-CLI-1's promise, which this
  change is what fulfils — and the evidence.

What the reviewer left for Gate 2 in its own words: the implementation and the
process tests actually running.

## Blockers

None.
