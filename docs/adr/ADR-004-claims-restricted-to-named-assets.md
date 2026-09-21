# ADR-004: A claim may name the assets whose work it wants

**Date:** 2026-09-21
**Status:** accepted
**Related:** refines ADR-003 (the queue and its claim); authored by the OpenSpec change `add-folder-indexing-cli`

## Context

ADR-003 fixed the claim: the rows that are pending and due, plus the rows whose lease has expired, ordered by when they became due, `FOR UPDATE SKIP LOCKED`. It also said what it did not decide — "the queue is first due, first served, with no priorities and no fairness between assets" — and that was true of every runner that existed: the drain an upload schedules, and the worker process of change 13. None of them cares which asset it is working for.

`index-folder` does. It creates work — one job per enabled model for every picture it imports — and it promises the operator that when it returns, those pictures are indexed. With a claim that takes whatever is due, that promise cannot be kept: a queue holding a thousand older jobs answers every claim with older jobs, and the import's own work waits behind them however many times it claims. The first draft of the change tried to bound the loop by the number of assets it created; Gate 1 refused it, correctly — the bound does not make the claims land on the right rows.

Two facts frame the decision. The claim query is already indexed on `(status, available_at)` and already takes a `LIMIT`; adding one more predicate to it changes nothing about how it is planned at this scale (measured in ADR-003: 0.3 ms over a thousand due rows). And the alternative way to keep the promise — watch the queue and hope — is what the change tried first.

## Decision

**A claimer may pass a set of asset identifiers, and a claim that carries one takes only those assets' work.** `IndexingJobRepository.claim` and `claim_statement` take an optional `asset_ids`; `run_batch` and `drain` pass it through. A claim that names no assets is unchanged in every respect — the same query, the same plan, the same behaviour — which is why every caller from changes 5 and 6 keeps working untouched and their tests stay green as written.

A restricted claim is a claim in every other way:

- one runner at a time: it locks with `FOR UPDATE SKIP LOCKED` like any other, so two restricted claimers over the same asset take its work once between them;
- the same lease, the same attempt count, the same conditional finishes bound to the lease;
- the same order among the rows it may take: first due, first served **within what it named**.

**What this does not change.** The queue's order is still first due, first served for every claimer that does not restrict itself, which is every runner that serves requests. There are no priorities: a restriction is not a rank, and nothing can make one job jump ahead of another inside the same claim. And a restricted claimer has no more right to a row than anyone else — a lease another runner holds is not available to it either.

**What it costs.** A runner finishing its own import can take rows ahead of older ones it did not create. That is the point, and it is bounded: the import claims only work it made moments ago, in batches of `WORKER_BATCH_SIZE`, and it stops as soon as none of its own work is claimable. Nothing else in the service uses the restriction.

## Alternatives considered

**Bound the loop instead of the claims** (the change's first draft). Call the existing drain a number of times derived from the assets created, and assume the import's work will be among what it takes. It cannot be assumed: with more older due work than the bound allows, every pass does someone else's work and the import returns with its own still pending — while reporting success. Refused at Gate 1.

**Watch, do not claim.** Let the import wait for another runner to do the work, polling `index_status` until it is done. Stage 1 has no other runner — the API's drain only runs when a request arrives — so an import into an idle service would wait forever, and with a worker it would be a race with no upper bound.

**A separate queue for imports.** A second table, or a column that marks work as "someone is waiting for this". It is a scheduler, which ADR-003 refused for the same reason it refused a broker: the state would have to be kept somewhere, and the somewhere is this table. A predicate on a query is not a scheduler.

**Finish the work inline, outside the queue.** The import has the pictures; it could embed them without going through `indexing_jobs` at all. That would give the import a second path to a vector, with its own failure and retry semantics, and it would break the rule the queue exists for: a vector is written in the same transaction that finishes the work that produced it. Refused.

## Consequences

- An operator command can promise what it delivers: `index-folder` returns when its own assets are indexed, or reports exactly what it left queued and why.
- The claim gained one optional argument and no new behaviour for anyone who does not pass it; the queue's contract in `openspec/specs/indexing-jobs/spec.md` gained one requirement clause and two scenarios.
- The worker of change 13 may use the same restriction if it ever needs to (it does not today), and `reindex` could target its own reset if that turns out to matter.
- A probe removes the predicate and watches the restricted-claim test fail, so the restriction cannot quietly stop restricting.

## Supersedes

No ADR clause. It refines ADR-003's "first due, first served", which remains true of every unrestricted claim — that is, of every runner that serves requests.
