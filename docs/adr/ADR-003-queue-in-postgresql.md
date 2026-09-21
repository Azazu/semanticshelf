# ADR-003: The indexing queue is a table in PostgreSQL, claimed with leases

**Date:** 2026-09-21
**Status:** accepted
**Related:** ADR-001 (the embeddings layout the queue writes into); authored by the OpenSpec change `add-background-indexing`

## Context

An uploaded picture becomes searchable only once a model has turned it into a vector. That work cannot happen in the request: a forward pass takes seconds on CPU, and the caller is waiting for a 201. So there is work to hand over, and something has to hold it between the upload that creates it and the runner that does it.

What the handover must survive is not exotic, but all of it is real:

- The process holding a unit of work can die — a deployment, an OOM kill, a `docker compose down` in the middle of a batch. The work must come back without an operator.
- Two runners will exist. Stage 1 drains in the API process; change 13 adds a `worker` process, and several of those may run at once. They must not do the same work twice.
- Delivery cannot be exactly-once. Anything that crosses a process boundary and a transaction boundary is at-least-once; the only question is whether the effect is idempotent.
- The state has to be visible. An operator asking "why has this asset no vectors" needs an answer with attempts, timestamps and a reason — not a message that was consumed and is gone.

The service already depends on PostgreSQL 16 for everything else, including the vectors themselves. A broker would be a second piece of infrastructure, a second failure mode, and a second place where state lives — while the state that matters (which asset, which model, how many attempts, what went wrong) would still have to live in the database to be queryable at all.

Measured on this machine, PostgreSQL 16.14 in the project's `pgvector/pgvector:pg16` container, 2000 jobs of which 1000 are due, after `ANALYZE` (`EXPLAIN (ANALYZE, BUFFERS)`, buffer lines dropped here):

```text
Limit  (cost=91.06..91.11 rows=4 width=30) (actual time=0.272..0.275 rows=4 loops=1)
  ->  LockRows  (cost=91.06..103.56 rows=1000 width=30) (actual time=0.271..0.273 rows=4 loops=1)
        ->  Sort  (cost=91.06..93.56 rows=1000 width=30) (actual time=0.267..0.267 rows=4 loops=1)
              Sort Key: available_at
              ->  Bitmap Heap Scan on indexing_jobs  (actual time=0.030..0.179 rows=1000 loops=1)
                    ->  BitmapOr
                          ->  Bitmap Index Scan on ix_jobs_claim
                                Index Cond: ((status = 'pending') AND (available_at <= now()))
                          ->  Bitmap Index Scan on ix_jobs_claim
                                Index Cond: (status = 'running')
Planning Time: 0.177 ms
Execution Time: 0.295 ms
```

One claim of four jobs took 9.0 ms end to end (connection and transaction included); four claimers running at once took 14.7 ms together, took four jobs each, and overlapped on nothing — sixteen distinct rows, none claimed twice.

## Decision

**The queue is the `indexing_jobs` table, and a claim is one transaction.** There is no broker, no Redis, no Celery. A runner claims with the query the requirements fix:

```sql
SELECT id FROM indexing_jobs
WHERE (status = 'pending' AND available_at <= now())
   OR (status = 'running' AND lease_expires_at < now())
ORDER BY available_at
LIMIT :batch
FOR UPDATE SKIP LOCKED
```

and, in the same transaction, sets the rows to `running`, counts an attempt and writes `lease_expires_at = now() + JOB_LEASE_SECONDS`. The transaction commits before any work starts, so a crash can lose the work but never the fact that the rows were taken.

**`SKIP LOCKED` is what makes two claimers disjoint** without anything outside the database. A claimer passes over rows another claimer holds rather than waiting for them. The difference from plain `FOR UPDATE` is not visible in the obvious test — with one row and two claimers, a blocking claimer re-reads and finds nothing, which looks identical — so it is tested with two due rows, one held inside an open transaction, and a deadline the test enforces; removing the clause makes that test fail by timing out.

**A lease, not a heartbeat.** A claim is good for a fixed time and nothing refreshes it. Work whose lease has expired is claimable again by the branch above, which is why the same query serves both cases. A heartbeat would need a second mechanism running while work is in flight, would still be a lease with a shorter period, and would fail exactly when the runner is too busy or too dead to send it. The cost is stated rather than hidden: work that legitimately takes longer than the lease is claimed a second time while the first runner is still going. The default — ten minutes against a forward pass of seconds — makes that unlikely, and the next decision makes it harmless.

**The lease timestamp is also the claim's token, and every finish carries it.** A finish updates `WHERE id = :id AND status = 'running' AND lease_expires_at = :owned_until`. Two claims of one row always carry different values, because a reclaim can only happen after the previous lease expired; a reset writes null, which invalidates every outstanding claim; a deleted asset takes the row with it. So a runner that comes back late — reclaimed, reset, or deleted under it — matches nothing, its whole transaction rolls back, and it discards its result instead of writing over the state of the runner that took over. The vector and the state change are in that one transaction, so neither lands alone.

`attempts` was rejected as the token: a reset clears it, so two different claims can carry the same value. A generation column was rejected as a migration this change does not need for a value the lease already provides.

**At-least-once, made harmless by the write.** The vector write is an upsert on `(asset_id, model)`, so executing the same unit twice leaves exactly one row, the second replacing the first. This is the price of the whole arrangement and it is paid once, in one statement.

**What this does not decide.** Nothing here is a scheduler: the queue is first due, first served, with no priorities and no fairness between assets. Nothing here bounds how long a runner may hold work beyond the lease. And the plan above shows the index serving the *predicate*, not the ordering: with a thousand due rows PostgreSQL bitmap-scans `ix_jobs_claim` twice and sorts. At this size that costs 0.3 ms and is not worth an index for; at a size where it is, the fix is an index that matches the ordering, which is a migration and a measurement, not a redesign.

## Alternatives considered

**A broker (Redis + RQ, or RabbitMQ + Celery).** The standard answer, and it loses on the shape of this service rather than on capability. The queue would be in one system and every question about it — which assets have no vectors, what failed and why, how many attempts a job has had — would still have to be answered from the database, because that is where the assets are. A second store means a second thing to run in `docker compose`, a second thing to back up, and a way for the two to disagree: a job acknowledged in the broker whose transaction rolled back, or the reverse. Enqueueing inside the asset's transaction, which is what makes "an asset never exists without its work" true, is not possible across two systems without an outbox — and an outbox is this table.

**`LISTEN`/`NOTIFY` to wake runners.** Attractive, and orthogonal: it removes polling latency but decides nothing about ownership, retries or visibility, and a notification is lost if no one is listening, so the table would still be the truth. It stays available as an optimisation once a worker process exists (change 13) and the polling interval starts to matter.

**`FOR UPDATE` without `SKIP LOCKED`.** One fewer keyword and the correctness is the same, but claimers serialise on each other: the second waits for the first's transaction instead of taking free work. With a batch of four and two runners that is a queue behind a queue, for no gain.

**Advisory locks as ownership.** `pg_try_advisory_lock` on the job id would hold ownership for the life of a session rather than for a lease. It ties ownership to a connection — a pooled connection, at that — and gives nothing to look at afterwards: a lock is not a row, so "who holds this and since when" has no answer in the API. The media root already uses advisory locks for the one thing they are good at, which is a short critical section inside one transaction.

**A status column without a lease** (just `pending` → `running` → `done`). This is the arrangement that strands work: a runner that dies leaves a row in `running` that nothing ever reclaims, and the fix is an operator with a `UPDATE`. The lease *is* the difference between a queue and a state column.

## Consequences

- One piece of infrastructure, one backup, one transaction boundary. Enqueue is part of the upload's transaction, so an asset and its work are created together or not at all — demonstrated by removing that and watching the test fail.
- Every question an operator asks has a SQL answer, and the API exposes them: `index_status` per model, the jobs of an asset with attempts and the last reason, and a reset that is the only way failed work runs again.
- A dead runner costs one lease period of latency and nothing else. No supervisor, no reaper, no operator.
- Work that outlives its lease is executed twice. Accepted, and bounded by the upsert; a longer-running model (DINOv2 on CPU, a large batch) is a reason to raise `JOB_LEASE_SECONDS`, not to add a heartbeat.
- The claim costs a round trip and a write per batch, and the table grows one row per asset per model. At the scale this service is built for that is nothing; at a scale where it is not, the row is still the cheapest place to look first.
- Polling, not pushing: a job that becomes due waits for the next run of a runner. In stage 1 that run is the next upload, which is the case that matters; change 13's worker loop is what makes it independent of traffic.
- The lease as a token means every finishing statement must carry it. That is three statements — done, returned to the queue, exhausted — and each has a probe that removes the condition from that one statement and watches its own test fail.

## Supersedes

No ADR clause.
