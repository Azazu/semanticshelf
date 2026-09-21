## 1. Settings and the queue's vocabulary

- [x] 1.1 Add the three settings to `app/core/settings.py`: the lease in seconds (default 600), the maximum attempts (default 3), the batch a runner drains (default 4); each validated as positive. Verify: `tests/unit/test_settings_indexing.py` asserts every default by value, refuses a non-positive value, and reads each through the environment as well as the constructor.
- [x] 1.2 Extend `app/repositories/jobs.py` with the claim query the requirements fix (pending and due, or running with an expired lease; ordered by when it became due; bounded; `FOR UPDATE SKIP LOCKED`) and the transitions a job can make: claimed, finished, returned to the queue with backoff, exhausted, reset. Verify: `tests/unit/test_backoff.py` covers the delay formula at each attempt, and the integration tests below cover the query itself.
- [x] 1.3 Expose the claim statement the way `app/repositories/embeddings.py` exposes its vector query, so a test can read its plan. Verify: an integration test asserts the plan uses `ix_jobs_claim` rather than a sequential scan.

## 2. Enqueue with the asset

- [x] 2.1 The upload creates one job per enabled model inside the transaction that stores the asset. Verify: an integration test asserts an uploaded asset has one job per enabled model, and that a failure storing the asset leaves neither the asset nor any job.
- [x] 2.2 An asset uploaded while no model is enabled gets no work and says so rather than failing. Verify: an integration test with an empty enabled set.

## 3. Claim, execute, finish

- [x] 3.1 Write `app/services/indexing.py`: `claim` in its own transaction (rows to `running`, attempt counted, lease set, the claim's token returned), `execute` outside any transaction (inspect the stored original again, then embed through the inference pool), `finish` in one transaction that writes the vector and the job's new state together (design decisions 3 and 9). Verify: unit tests with the fake embedder cover the happy path and each failure branch; the integration tests of section 5 cover the transactions.
- [x] 3.2 Every finishing statement — done, returned to the queue, exhausted — carries the claim's token and takes effect only while it is still current (design decision 9). When it matches nothing the transaction rolls back, the runner discards its result and records the fact, without retrying and without a server error. Verify: unit tests for the "matched nothing" branch and the integration tests of tasks 5.5-5.7.
- [x] 3.3 The stored original is inspected again before it is decoded (design decision 10): format from the bytes, pixel cap, minimum side, and conversion to three channels before the model sees it. Verify: integration tests replace a stored file with one that would be refused at upload, with one beyond the pixel cap, and with a greyscale picture that must succeed.
- [x] 3.4 Failure handling: a failing job returns to the queue with the computed backoff while attempts remain, and is marked failed once they are spent. The reason names the failure's class, and carries its message only for the failures the indexing code raises itself — for anything else the class alone, because no rule can tell which parts of a library's message came from the picture it was reading (design decision 11). Both forms are bounded to two kilobytes with the truncation visible, and never carry a stack trace. Verify: unit tests for both outcomes, for the byte bound at its boundary, for a foreign exception whose message holds file bytes (class only), for one of the service's own (class and message), and for a traceback.
- [x] 3.5 Work whose asset was deleted mid-flight: the finish matches nothing because the row went with the asset, the runner discards its result and continues with the rest of its batch. Verify: an integration test deletes the asset while a job is in flight and asserts no vector, no job, and a runner that carried on.
- [x] 3.6 A job naming a model this build does not have enabled ends as failed with a reason rather than waiting forever. Verify: a unit test.

## 4. The runner in the API process

- [x] 4.1 Drain a bounded batch after the upload response through FastAPI's background tasks, using its own session rather than the request's. Verify: an integration test uploads a picture and finds its vectors present shortly after the response, without the response having waited.
- [x] 4.2 The drain takes at most the configured batch and does not loop while work remains. Verify: an integration test with more jobs than the bound asserts what one run took and what it left.
- [x] 4.3 Model work goes through the inference pool of change 4, never the event loop. Verify: a test asserts the loop keeps making progress while a slow embed is in flight, in the shape of the pool tests from that change.

## 5. Concurrency, against a real database

- [x] 5.1 The claim passes over rows another claimer holds rather than waiting for them: with two due jobs, one held inside an open transaction, a second claimer takes the other **within a deadline the test enforces**. Without `SKIP LOCKED` the second claimer blocks instead, which is what makes this observable (the naive "one job, two claimers" test cannot tell the two apart). Verify: an integration test with two sessions and a bounded wait.
- [x] 5.2 Two claimers, one job: exactly one gets it, the other gets nothing, and the job is attempted once. Verify: an integration test with two sessions claiming concurrently.
- [x] 5.3 An expired lease is reclaimed exactly once and counts a new attempt; a valid lease is not reclaimable. Verify: two integration tests.
- [x] 5.4 A duplicate delivery leaves exactly one vector: execute the same job twice and assert one row for that asset and model, with the second write replacing the first. Verify: an integration test.
- [x] 5.5 A crash between the vector and the finish leaves neither: fail inside the finishing transaction and assert no vector and an unfinished job. Verify: an integration test.
- [x] 5.6 A late success after a reclaim changes nothing: A claims, its lease expires, B reclaims, then A finishes. B's state stands and no vector from A is written. Verify: an integration test.
- [x] 5.7 A late retry after a reclaim changes nothing: A reports a failure with attempts remaining while B holds the job. B's attempts, state and due time stand. Verify: an integration test.
- [x] 5.8 A late exhaustion after a reclaim changes nothing: A reports its last failure while B holds the job; the job does not become failed on A's word. Verify: an integration test.
- [x] 5.9 A late finish after a reset changes nothing: the reset's clean state stands. Verify: an integration test.

## 6. What the API shows

- [x] 6.1 `index_status` in the asset representation: the newest job per model, derived rather than stored. Verify: an integration test covering an asset with work done, one with work waiting and one whose work failed.
- [x] 6.2 The listing filter on the state of the work, with 422 for an unknown model or state. Verify: api and integration tests for each case.
- [x] 6.3 The jobs of an asset: attempts, timestamps and last reason; 404 for an identifier that is not stored. Verify: integration tests.
- [x] 6.4 The reset: chosen models or all of them, attempts cleared, reason cleared, state back to pending, 404 for an unknown asset, and the answer says what was reset. Verify: integration tests including a reset of failed work that then succeeds.

## 7. Failing inputs (high tier: one per new check)

One row per new guard, one probe per row; each removes exactly that guard,
runs the named test, records the output in the commit body and restores the
code.

| New check | Probe |
|---|---|
| Lease setting must be positive | 7.1 |
| Attempts setting must be positive | 7.2 |
| Batch setting must be positive | 7.3 |
| Enqueue inside the asset's transaction | 7.4 |
| `SKIP LOCKED` in the claim | 7.5 |
| The expired-lease branch of the claim | 7.6 |
| A valid lease is not reclaimable | 7.7 |
| Vector and finish in one transaction | 7.8 |
| The claim token on the done transition | 7.9 |
| The claim token on the retry transition | 7.9a |
| The claim token on the exhausted transition | 7.9b |
| The reset clearing the token (a late finish after a reset cannot land) | 7.10 |
| The upsert that makes a repeat harmless | 7.11 |
| Backoff on a retry | 7.12 |
| The attempt bound | 7.13 |
| Work whose asset is gone ends quietly | 7.14 |
| A job naming a disabled model ends instead of waiting | 7.15 |
| The batch bound of the drain | 7.16 |
| The reason carrying no stack trace | 7.17 |
| The reason's two-kilobyte bound | 7.18 |
| A foreign failure's message is dropped, leaving the class | 7.19 |
| The service's own failure keeps its message | 7.19a |
| Re-inspection of the stored file (format and caps) | 7.20 |
| Conversion to three channels before inference | 7.21 |
| The listing filter refusing an unknown model or state | 7.22 |

- [ ] 7.1 Remove the positive bound on the lease setting: its test fails.
- [ ] 7.2 Remove the positive bound on the attempts setting: its test fails.
- [ ] 7.3 Remove the positive bound on the batch setting: its test fails.
- [ ] 7.4 Enqueue outside the asset's transaction: the test that a failed store leaves no jobs fails.
- [ ] 7.5 Remove `SKIP LOCKED`: the pass-over test of task 5.1 fails, because the second claimer waits for the held row instead of taking the free one.
- [ ] 7.6 Remove the expired-lease branch from the claim: the reclaim test fails.
- [ ] 7.7 Widen the lease comparison to include valid leases: the test that a fresh claim is not reclaimable fails.
- [ ] 7.8 Finish the job in a transaction separate from the vector: the crash test fails, showing a vector whose work is unfinished.
- [ ] 7.9 Remove the token from the `done` statement alone: the late-success test fails, showing A's result over B's state.
- [ ] 7.9a Remove the token from the retry statement alone: the late-retry test fails, showing A's backoff over B's attempt.
- [ ] 7.9b Remove the token from the exhausted statement alone: the late-exhaustion test fails, showing a job failed on A's word while B held it.
- [ ] 7.10 Leave the token alone on reset: the late-finish-after-reset test fails.
- [ ] 7.11 Turn the upsert into an insert: the duplicate-delivery test fails.
- [ ] 7.12 Remove the backoff: the retry test fails, showing a job due immediately.
- [ ] 7.13 Remove the attempt bound: the exhaustion test fails, showing a job that never reaches failed.
- [ ] 7.14 Treat a finish that matched nothing as an error: the deleted-asset test fails with a server error instead of a quiet end.
- [ ] 7.15 Remove the enabled-model check from execution: the disabled-model test fails.
- [ ] 7.16 Remove the batch bound: the drain test fails, showing more work taken than allowed.
- [ ] 7.17 Put the exception's traceback in the reason: that test fails.
- [ ] 7.18 Remove the two-kilobyte truncation: the boundary test fails.
- [ ] 7.19 Record the message of every failure, whatever raised it: the foreign-exception test fails, showing the picture's bytes in the record.
- [ ] 7.19a Record only the class for every failure: the test that the service's own message survives fails, which is what keeps the rule from degenerating into "say nothing".
- [ ] 7.20 Skip the re-inspection and decode the stored file directly: the replaced-file tests fail.
- [ ] 7.21 Remove the conversion to three channels: the greyscale test fails.
- [ ] 7.22 Accept any model or state in the filter: that test fails.

## 8. Decision record and documentation

- [ ] 8.1 Write `docs/adr/ADR-003-*.md`: why the queue is a table in PostgreSQL, what the claim query is and what it guarantees, why a lease rather than a heartbeat, and what at-least-once costs. Verify: re-read whole; the ADR index lists it.
- [ ] 8.2 Extend `docs/how-to/uploading.md` (or a new how-to) with watching the work: reading `index_status`, listing an asset's jobs, resetting failed work, and what each state means. Verify: every command run in its exact form, output pasted from the run.
- [ ] 8.3 Extend `docs/reference/settings.md` with the three settings and the AGENTS.md layout with the indexing service. Verify: both re-read whole.

## 9. Wrap-up

- [ ] 9.1 Commits per logical block, no agent trailers, each body naming the evidence for the tasks its diff holds. Verify: `git log --format=%B main..HEAD | grep -c '^Co-Authored-By'` prints `0`.
- [ ] 9.2 `env -u DATABASE_URL make check` green and `make test-integration` green against pgvector. Verify: both outputs recorded in a commit body.
- [ ] 9.3 Acceptance on GitHub (the user pushes the branch): both jobs green. Verify: the user reports the run.
- [ ] 9.4 `openspec validate add-background-indexing --strict` and `scripts/pregate-verify.sh gate2 add-background-indexing` pass; request Gate 2 with `/gate-review add-background-indexing 2`.
