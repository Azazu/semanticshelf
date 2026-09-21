## 1. Settings and the queue's vocabulary

- [ ] 1.1 Add the three settings to `app/core/settings.py`: the lease in seconds (default 600), the maximum attempts (default 3), the batch a runner drains (default 4); each validated as positive. Verify: `tests/unit/test_settings_indexing.py` asserts every default by value, refuses a non-positive value, and reads each through the environment as well as the constructor.
- [ ] 1.2 Extend `app/repositories/jobs.py` with the claim query the requirements fix (pending and due, or running with an expired lease; ordered by when it became due; bounded; `FOR UPDATE SKIP LOCKED`) and the transitions a job can make: claimed, finished, returned to the queue with backoff, exhausted, reset. Verify: `tests/unit/test_backoff.py` covers the delay formula at each attempt, and the integration tests below cover the query itself.
- [ ] 1.3 Expose the claim statement the way `app/repositories/embeddings.py` exposes its vector query, so a test can read its plan. Verify: an integration test asserts the plan uses `ix_jobs_claim` rather than a sequential scan.

## 2. Enqueue with the asset

- [ ] 2.1 The upload creates one job per enabled model inside the transaction that stores the asset. Verify: an integration test asserts an uploaded asset has one job per enabled model, and that a failure storing the asset leaves neither the asset nor any job.
- [ ] 2.2 An asset uploaded while no model is enabled gets no work and says so rather than failing. Verify: an integration test with an empty enabled set.

## 3. Claim, execute, finish

- [ ] 3.1 Write `app/services/indexing.py`: `claim` in its own transaction (rows to `running`, attempt counted, lease set), `execute` outside any transaction (read the stored original, embed through the inference pool), `finish` in one transaction that writes the vector and the job's new state together (design decision 3). Verify: unit tests with the fake embedder cover the happy path and each failure branch, and the integration tests of section 5 cover the transactions.
- [ ] 3.2 Failure handling: a failing job returns to the queue with the computed backoff while attempts remain, and is marked failed with a short reason once they are spent. The reason names the failure without a stack trace and without file content. Verify: unit tests for both outcomes and for the shape of the reason.
- [ ] 3.3 A job whose asset is gone ends as failed with `asset-deleted` on the first attempt, without a retry. Verify: an integration test deletes the asset while a job is in flight and asserts the job's end state and that it is not retried.
- [ ] 3.4 A job naming a model the build does not have enabled fails with a reason rather than waiting forever. Verify: a unit test.

## 4. The runner in the API process

- [ ] 4.1 Drain a bounded batch after the upload response through FastAPI's background tasks, using its own session rather than the request's. Verify: an integration test uploads a picture and finds its vectors present shortly after the response, without the response having waited.
- [ ] 4.2 The drain takes at most the configured batch and does not loop while work remains. Verify: an integration test with more jobs than the bound asserts what one run took and what it left.
- [ ] 4.3 Model work goes through the inference pool of change 4, never the event loop. Verify: a test asserts the loop keeps making progress while a slow embed is in flight, in the shape of the pool tests from that change.

## 5. Concurrency, against a real database

- [ ] 5.1 Two claimers, one job: exactly one gets it, the other gets nothing, and the job is attempted once. Verify: an integration test with two sessions claiming concurrently.
- [ ] 5.2 An expired lease is reclaimed exactly once, and counts a new attempt; a valid lease is not reclaimable. Verify: two integration tests.
- [ ] 5.3 A duplicate delivery leaves exactly one vector: execute the same job twice and assert one row for that asset and model, with the second write replacing the first. Verify: an integration test.
- [ ] 5.4 A crash between the vector and the finish leaves neither: simulate a failure inside the finishing transaction and assert no vector and an unfinished job. Verify: an integration test.

## 6. What the API shows

- [ ] 6.1 `index_status` in the asset representation: the newest job per model, derived rather than stored. Verify: an integration test covering an asset with work done, one with work waiting and one whose work failed.
- [ ] 6.2 The listing filter on the state of the work, with 422 for an unknown model or state. Verify: api and integration tests for each case.
- [ ] 6.3 The jobs of an asset: attempts, timestamps and last reason; 404 for an identifier that is not stored. Verify: integration tests.
- [ ] 6.4 The reset: chosen models or all of them, attempts cleared, reason cleared, state back to pending, 404 for an unknown asset, and the answer says what was reset. Verify: integration tests including a reset of failed work that then succeeds.

## 7. Failing inputs (high tier: one per new check)

One row per new guard, one probe per row; each removes exactly that guard,
runs the named test, records the output in the commit body and restores the
code.

| New check | Probe |
|---|---|
| Enqueue inside the asset's transaction | 7.1 |
| `SKIP LOCKED` in the claim | 7.2 |
| The lease bound in the claim (an expired lease is reclaimable) | 7.3 |
| A valid lease is not reclaimable | 7.4 |
| Vector and finish in one transaction | 7.5 |
| The upsert that makes a repeat harmless | 7.6 |
| Backoff on a retry | 7.7 |
| The attempt bound | 7.8 |
| `asset-deleted` without a retry | 7.9 |
| The batch bound of the drain | 7.10 |
| The reason carrying no stack trace | 7.11 |
| The filter refusing an unknown model or state | 7.12 |

- [ ] 7.1 Enqueue outside the asset's transaction: the test that a failed store leaves no jobs fails.
- [ ] 7.2 Remove `SKIP LOCKED`: the two-claimers test fails (one blocks or both take the row).
- [ ] 7.3 Remove the expired-lease branch from the claim: the reclaim test fails.
- [ ] 7.4 Widen the lease comparison to include valid leases: the test that a fresh claim is not reclaimable fails.
- [ ] 7.5 Finish the job in a transaction separate from the vector: the crash test fails, showing a vector whose work is unfinished.
- [ ] 7.6 Turn the upsert into an insert: the duplicate-delivery test fails.
- [ ] 7.7 Remove the backoff (leave `available_at` alone): the retry test fails, showing a job due immediately.
- [ ] 7.8 Remove the attempt bound: the exhaustion test fails, showing a job that never reaches failed.
- [ ] 7.9 Retry the `asset-deleted` case like any other failure: that test fails.
- [ ] 7.10 Remove the batch bound: the drain test fails, showing more work taken than allowed.
- [ ] 7.11 Put the exception's traceback in the reason: the reason test fails.
- [ ] 7.12 Accept any model or state in the filter: that test fails.

## 8. Decision record and documentation

- [ ] 8.1 Write `docs/adr/ADR-003-*.md`: why the queue is a table in PostgreSQL, what the claim query is and what it guarantees, why a lease rather than a heartbeat, and what at-least-once costs. Verify: re-read whole; the ADR index lists it.
- [ ] 8.2 Extend `docs/how-to/uploading.md` (or a new how-to) with watching the work: reading `index_status`, listing an asset's jobs, resetting failed work, and what each state means. Verify: every command run in its exact form, output pasted from the run.
- [ ] 8.3 Extend `docs/reference/settings.md` with the three settings and the AGENTS.md layout with the indexing service. Verify: both re-read whole.

## 9. Wrap-up

- [ ] 9.1 Commits per logical block, no agent trailers, each body naming the evidence for the tasks its diff holds. Verify: `git log --format=%B main..HEAD | grep -c '^Co-Authored-By'` prints `0`.
- [ ] 9.2 `env -u DATABASE_URL make check` green and `make test-integration` green against pgvector. Verify: both outputs recorded in a commit body.
- [ ] 9.3 Acceptance on GitHub (the user pushes the branch): both jobs green. Verify: the user reports the run.
- [ ] 9.4 `openspec validate add-background-indexing --strict` and `scripts/pregate-verify.sh gate2 add-background-indexing` pass; request Gate 2 with `/gate-review add-background-indexing 2`.
