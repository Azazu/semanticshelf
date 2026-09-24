# Handoff — add-indexing-worker

**Updated:** 2026-09-24 · claude
**State:** proposing
**Branch:** change/add-indexing-worker

## Done this session

Branch and scaffold only.

## Next step

`/opsx:propose add-indexing-worker` — change 13 of the roadmap, tier `high`
(concurrency): the queue gets a process of its own.

What it is about, from `openspec/ROADMAP.md` and the requirements: a `worker`
command that drains `indexing_jobs` through the same claim/execute/finish
functions the in-request runner already uses (`app/services/indexing.py`), with
`FOR UPDATE SKIP LOCKED` across several processes, a graceful shutdown that
finishes the batch it holds rather than abandoning a lease, and the
`INDEXING_RUNNER` switch that decides which runner a deployment uses. The API
contract does not change — that is the point of the queue having been a table
in PostgreSQL since change 6.

Worth reading before proposing: `docs/adr/ADR-003-queue-in-postgresql.md`,
`docs/adr/ADR-004-claims-restricted-to-named-assets.md`, the `indexing-jobs`
spec, and change 6's archived design (the lease is both the expiry and the
token of ownership, and every finish checks it).

## Blockers

None.
