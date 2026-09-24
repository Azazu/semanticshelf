# Review — add-indexing-worker

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-24
**Reviewed-Commit:** 02a6fc6c9bad4e03c730ef881f5e98c50c9650a6
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `specs/indexing-jobs/spec.md:36–45`; `design.md` Applicability / Concurrent writers | The new scenarios promise exactly-once execution and no simultaneous duplicate execution without the preconditions that make those statements true. A live worker can exceed its lease while computing; another worker then reclaims and computes the same job. The unchanged claim/execute/finish mechanism permits this, as the design explicitly acknowledges and FR-IDX-3 requires. Qualify the normal concurrency scenario with valid leases and no retries, distinguish a terminated worker from a paused or slow one, and state the actual general guarantee: at-least-once execution with fenced completion and idempotent effects. Cover live lease expiry and a stale completion in the verification plan, referencing existing tests where sufficient. | fixed |
| 2 | major | `design.md` Decision 4; `tasks.md` section 4 and task 6.3 | The switch is planned only for upload and reindex, but normative FR-CLI-1 in `docs/explanation/requirements.md:127` explicitly says that from change 13 `INDEXING_RUNNER` also selects between the folder command's own runner and the worker process. Currently `app/cli.py::index_folder` passes `index=not no_index`, so implementing these tasks leaves `index-folder` computing locally under `INDEXING_RUNNER=worker`. Add the folder-command behavior, its interaction with `--no-index`, and implementation/verification coverage to the artifacts; alternatively explicitly reconcile the normative requirement if the intended scope is HTTP-only. Task 6.3 currently updates FR-IDX-2 and FR-CLI-2 but leaves this conflicting promise intact. | fixed |
| 3 | major | `proposal.md` What Changes / several workers; `design.md` Decision 6; `tasks.md` 2.3–2.4 and 3.1–3.3 | The proposal explicitly promises to prove shared-queue operation and dead-runner recovery with processes, but the design substitutes two tasks and permits only an empty-queue subprocess. That cannot exercise independent worker runtimes taking work or a real second signal terminating an active worker and leaving reclaimable jobs. Rejecting nonempty subprocess tests because they require real weights is not necessary: a test-only child-process harness can inject the existing fake embedder before invoking the worker adapter. Specify such process evidence with deterministic synchronization and real signals, or reconcile the claimed scope explicitly. Also correct task 3.2: both loops eventually taking work does not prove absence of lock waits; a blocking claim can pass that assertion. Reuse the existing held-transaction/timeout test (`tests/integration/test_indexing.py::test_a_claimer_passes_over_work_another_holds`) as the authority or plan an equivalent deterministic check. | fixed |
| 4 | minor | `specs/indexing-jobs/spec.md:58`; `design.md` Decision 3; `tasks.md` 5.2 | The spec requires an ending report for both graceful and forced shutdown, whereas the second-signal design restores the default disposition and terminates immediately, bypassing the normal return/finally reporting path. The planned output test covers only graceful shutdown. Either limit the final-summary guarantee to graceful shutdown and document forced termination as best effort, or specify and verify what can be reported before re-signalling without delaying the forced exit. | fixed |

### Validation

- Verified that the clean working tree was on `change/add-indexing-worker` at the requested commit before review.
- Read the proposal, design, tasks, delta specification, handoff, repository instructions and OpenSpec configuration; checked relevant living requirements, queue implementation, CLI adapters and existing concurrency tests.
- `openspec validate add-indexing-worker --strict` passed. This validates artifact structure, not the semantic contradictions above.
- Gate 1 artifact review only; no implementation changes or git write commands.

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-24
**Reviewed-Commit:** 601dc9ee52aeb117f57764e30a157874551894ff
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | changes-requested — The general at-least-once guarantee, normal-case lease preconditions, live-expiry scenario and task 3.4 now address most of the finding. However, `specs/indexing-jobs/spec.md:56–60` still retains the original unqualified promise that work from a runner that is "stopped" is "never executed twice at the same time". A paused runner can resume after reclamation; even a replacement for a terminated runner can itself outlive its lease. Explicitly require termination of the original process and valid leases/no retries for the replacement scenario, or replace its no-overlap assertion with fenced completion and idempotent effects. The new general paragraph does not remove this contradictory scenario. |
| 2 | confirmed — Proposal and design decision 4 now include `index-folder` and `index missing`; the delta spec covers commands leaving work queued. Tasks 4.4–4.5 cover implementation, both setting values, `--no-index` combinations, truthful summaries and folder-to-worker integration. Task 6.3 explicitly reconciles FR-CLI-1. |
| 3 | changes-requested — Real child processes with fake models and reuse of the held-transaction no-wait test are now planned. Deterministic synchronization is still missing: design decision 6 and tasks 2.4–2.5 observe queue state but never hold the child at that state. The existing fake embedder has no barrier; after the parent observes `running`, the child can finish or claim another batch before the signal arrives. Two SIGTERMs without acknowledgement of the first can also coalesce or arrive after graceful exit, so they do not reliably exercise forced termination with unfinished work. Specify a test-only execution barrier and parent/child acknowledgement: hold claimed work while delivering and acknowledging the first signal, release it for the graceful test, or deliver the second while it remains held for the forced test. Also coordinate both children before releasing their claimed batches so task 3.1 cannot depend on startup timing to make both perform work. |

### Validation

- Confirmed the branch and HEAD match the requested review target and the working tree was initially clean.
- Reviewed only the specified commit diff and collateral relevant to findings 1–3, including the existing fake embedder, fencing tests, held-transaction test and CLI requirement. No unrelated minor findings added.
- `openspec validate add-indexing-worker --strict` passed; this is structural validation, not proof of the outstanding concurrency claims.
- Gate 1 artifact confirmation only. Modified only `review.md`; ran no git write commands.
