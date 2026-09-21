# Design — add-background-indexing

## Context

See `proposal.md` — Why. What exists: the `indexing_jobs` table with the two
indexes this change needs (`ix_jobs_claim` on `(status, available_at)`,
`ix_jobs_asset` on `(asset_id, model, created_at desc)`), a repository that can
add jobs and close them, embedders behind one protocol with a pool that keeps
model work off the event loop (change 4), and an upload that stores an asset in
one transaction (change 5). What does not exist: anything that runs after a
response, anything two processes execute at once, and any vector.

Constraints: `make check` must stay green without a database and without
weights, so the queue's behaviour is tested against the fake embedder and the
concurrency against a real PostgreSQL; the claim query's shape is fixed by the
requirements (§3.3) and is the mechanism ADR-003 will record.

## Goals / Non-Goals

**Goals:** an asset and its work are created together; work is claimed by one
runner at a time; a runner that dies releases its work without help; a repeat
of any delivery is harmless; failures retry a bounded number of times and then
say why.

**Non-Goals:** see `proposal.md` — Non-goals. At design level: no abstraction
over the queue (no broker interface with one implementation), and no
scheduling beyond "first due, first served".

## Applicability

| Question | Applies | How it is handled |
|---|---|---|
| Crash before/after an external effect | yes | The external effects are the vector and the job's completion. They are written in **one** transaction, so no crash can leave a vector with unfinished work or finished work without its vector. A crash while executing leaves the job `running` with a lease; when the lease expires the job is claimable again, and the upsert makes the repeat harmless. |
| Concurrent writers | yes | Several runners claim from one table. The claim is `SELECT … FOR UPDATE SKIP LOCKED` inside a transaction that immediately marks the rows `running`: a row is either locked (invisible to others) or already `running` with a fresh lease. Two claimers therefore never take the same row, and an integration test runs both against a real database rather than asserting it. |
| Money rounding | n/a | No money anywhere in the project. |
| Empty/zero/null inputs | yes | An asset uploaded while no model is enabled gets no work and reports an empty status map rather than a lie. A job naming a model that is no longer enabled fails with a reason instead of hanging in the queue forever. A reset with no models named resets all of the asset's work. |
| Authorization boundary | yes | None exists (single-tenant, unauthenticated). What matters instead is that the reset endpoint cannot be used to make the service do unbounded work: it only clears attempts on work that already exists for an asset that exists. |
| Deletion/expiry | yes | Two kinds. An asset deleted mid-flight takes its job row with it (`ON DELETE CASCADE`), so there is **nothing left to mark failed** — the conditional finish of decision 9 simply matches no row, the whole transaction rolls back, and the runner discards its result and moves on. (Gate 1 finding 1: the requirement and this table both claimed a `failed: asset-deleted` end state the schema cannot hold; FR-IDX-6 is corrected in this change.) A lease expiring is the other kind: it makes work claimable again, which is the mechanism for a dead runner, and decision 9 is what keeps the dead runner from overwriting its successor. |
| Idempotency of retries | yes | Delivery is at-least-once by design. The embedding write is an upsert on `(asset_id, model)`, so a second execution replaces the first vector rather than adding one; the finish is part of the same transaction, so a repeat cannot double-count anything. |

## Decisions

1. **The queue is the table, and the claim is the query the requirements
   fix.** `SELECT … WHERE (status = 'pending' AND available_at <= now()) OR
   (status = 'running' AND lease_expires_at < now()) ORDER BY available_at
   LIMIT :n FOR UPDATE SKIP LOCKED`, followed by an update to `running` in the
   same transaction. `SKIP LOCKED` is what makes two claimers disjoint without
   any coordination outside the database.
   Rejected: a broker (Redis, RabbitMQ) — a second piece of infrastructure, a
   second failure mode and a second place for state that must agree with the
   database; and advisory locks per job — they solve the same problem with a
   mechanism the queue's own rows already provide. ADR-003 records this.

2. **Three functions, one protocol: `claim`, `execute`, `finish`.** The
   stage-1 runner in the API process and the worker process of change 13 call
   the same three. Writing them now, and proving them under concurrency now,
   is what makes that later change small.

3. **The transaction boundaries are the design.** `claim` runs in its own
   transaction and commits (the rows are `running` with a lease before any
   work starts, so a crash cannot lose the fact that they were taken).
   `execute` runs outside a transaction: it reads a file and runs a model,
   which must not hold a database connection. `finish` opens a new transaction
   and writes the vector **and** the job's new state together — conditionally,
   as decision 9 describes.

4. **A lease, not a heartbeat.** A claim sets `lease_expires_at = now +
   JOB_LEASE_SECONDS`; nothing refreshes it. A runner that dies releases its
   work when the lease expires, with no daemon to watch it and nothing to
   clean up by hand. The cost is that work which legitimately takes longer
   than the lease may be claimed twice — which the idempotent write makes
   harmless, and which the default (ten minutes against a forward pass of
   seconds) makes unlikely.

5. **The model runs on the inference pool of change 4.** The runner acquires
   the embedder through `app/ml/pool.acquire` and embeds through the same
   pool, so indexing never blocks the event loop and never competes with file
   reads. The stage-1 runner also drains at most `WORKER_BATCH_SIZE` jobs per
   run: a background task that loops while work remains is a background task
   that never ends.

6. **Backoff is computed, not stored.** `available_at = now + 2^attempts ×
   10s` at the moment of failure, as the requirements state; there is no
   scheduler and nothing to wake up. A job becomes due because time passed.

7. **`index_status` is derived, never stored.** One query over
   `(asset_id, model, created_at desc)` gives the newest job per model. Storing
   a status on the asset would be a second copy of the truth, and the index
   that makes the derivation cheap already exists.

8. **A reset clears attempts; it does not delete and recreate.** The job keeps
   its identity and its history (`attempts` back to zero, `last_error`
   cleared, `status` back to `pending`), so an operator can see that it ran
   before. Deleting and inserting would lose that and would race with a runner
   holding the row.

9. **A finish only lands while the claim still owns the work.** A lease alone
   is not enough: once A's lease expires, B may reclaim, and A — still alive,
   merely slow — would otherwise commit its result over B's. Every finishing
   statement therefore carries the token its claim handed out and updates
   `WHERE id = :id AND status = 'running' AND lease_expires_at = :token`. The
   lease timestamp *is* the token: a reclaim can only happen after the previous
   lease expired, so two claims of one row always carry different values, and a
   reset clears it to null, which invalidates any outstanding claim. When the
   update matches nothing — reclaimed, reset, or the asset and its row deleted
   — the whole transaction rolls back, so the vector is not written either, and
   the runner discards its result and logs the fact.
   Rejected: `attempts` as the token (a reset clears it, so two different
   claims can carry the same value); a new generation column (a migration this
   change does not need, for a token the lease already provides).

10. **A stored file is inspected again before it is decoded** (FR-IDX-7). The
   runner passes the stored original through the same inspection an upload
   uses — format from the bytes, pixel cap, minimum side — and converts to
   three channels before the model sees it. The checks made at upload describe
   the file that arrived, not the file that is on disk now; a file replaced
   underneath the service must not reach the decoder on the strength of a
   check made about different bytes.

11. **A failure's reason carries a message only when the service wrote that
   message.** "Strip file bytes out of an arbitrary exception message" is not
   a mechanism — there is no way to recognise, in a string a third-party
   library produced, which parts came from a picture. So the rule is by origin
   rather than by inspection: this change defines a small set of failures the
   indexing code raises itself, whose messages it therefore controls (the
   model is not enabled, the stored file no longer passes inspection, the file
   is missing, the model failed to load). For those, the reason is the class
   and the message. For anything else — a library's exception, a driver's, an
   unexpected one — the reason is the class name alone, and the message is
   dropped rather than trusted.

   Both forms are then truncated to the two kilobytes the column allows, with
   the truncation visible. What is lost is diagnostic detail for unexpected
   failures; what is gained is a rule that can actually be enforced, and a
   test that can actually prove it: an exception whose message is a picture's
   bytes leaves nothing but its class name in the record.
   Rejected: scrubbing by pattern (unbounded and unprovable — any escape makes
   the security claim false); recording no message at all (loses the detail
   for exactly the failures the service is best placed to explain).

## Risks / Trade-offs

- [Work that outlives its lease is executed twice] → decision 4; the upsert
  makes it harmless, and the integration test for a duplicate delivery asserts
  exactly one vector.
- [The stage-1 runner shares the API process] → it drains a bounded batch and
  runs model work on the inference pool; the worker process of change 13 is
  the real answer for volume, and this change deliberately does not pretend to
  be it.
- [A job for a model that is no longer enabled] → it fails with a reason
  rather than blocking the queue; re-enabling the model and resetting the job
  is the operator's path.
- [`BackgroundTasks` runs only if the response was produced] → an upload that
  fails never enqueues a drain, which is correct: its asset does not exist.
  Work enqueued by an upload whose process then dies is picked up by the next
  drain, because the queue is in the database rather than in memory.

## Migration Plan

No schema change: change 3 created the table and both indexes. Deployment is
the new code. Assets uploaded before it have no work and no way to acquire any
— reset only clears the attempts of work that exists (decision 8), and
creating work for old assets is not in this change; there are no such assets
in any environment, and a change that needs it can add a command. Rollback is
the previous code: jobs already `pending` simply stay there until a runner
exists again.
