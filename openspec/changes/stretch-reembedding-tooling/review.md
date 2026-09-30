# Review — stretch-reembedding-tooling

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-30
**Reviewed-Commit:** 95669971444978df7d672f6f41d4f224e2ac5f89
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | design.md — Applicability / Concurrent writers; decision 3; tasks.md — 3.1 | Putting completeness inside a DELETE gives a statement snapshot, not serialization against another retirement. With an asset covered by A and B, simultaneous retirements A→B and B→A can each observe complete coverage, delete disjoint rows, and both commit, leaving neither vector. The existing per-model queue lock does not protect these deletes. Specify a retirement concurrency mechanism that protects both source and replacement keys across the coverage check and commit, with consistent lock ordering or another demonstrated serialization strategy; add a two-session regression and failing-input evidence. Also correct the upload example: an asset with no vector under either key is outside the specified old-key coverage predicate and cannot make that count refuse; the growth test must actually introduce an old-only vector. | fixed |
| 2 | major | design.md — decision 1; tasks.md — 2.1–2.3; specs/indexing-jobs/spec.md | Both commands are described as queuing and carrying out their work, but the plan never defines behavior under INDEXING_RUNNER=worker. The existing indexing-jobs requirement "Which runner carries out the work is configured" explicitly prohibits execution by operator commands in that configuration; app/cli.py:index_missing uses carries_out_work for that reason. Define the new commands' queue-only behavior, reporting and retirement behavior when replacement work is outstanding, and cover both runner configurations in specs and verification tasks. If an override is intended, it needs an explicit modification of the existing requirement and justification rather than an implicit exception. | fixed |
| 3 | major | proposal.md — Non-goals / No resume state; design.md — Applicability / Crash around an external effect; tasks.md — 2.1; specs/indexing-jobs/spec.md — A rebuild asked for twice | The claim that rerunning finishes an interrupted rebuild is not provided by the existing fill engine. queue_missing skips pending/running work, and backfill passes only newly queued asset IDs to finish_work. After a crash leaves pending work, or a running lease that later expires, a rerun can therefore queue nothing and drain nothing in an inline deployment with no separate worker. Specify how the shared engine includes previously outstanding selected work in execution/reporting without double-queuing it, how it reports a still-valid lease or delayed retry, and what happens to terminal failed work without violating the existing explicit-reset rule. Add recovery tests with no worker, including a pending job and an expired claim; distinguish completion from work merely left queued. | fixed |
| 4 | major | proposal.md — Why / ADR-007 repair; design.md — Context and Applicability / Concurrent writers; tasks.md — 2.2 and 4.3 | The same-key repair has no stated checkpoint-consistency precondition. An API or worker already running with the previous revision keeps its model cached per process (app/ml/registry.py), and queued jobs carry a key, not a checkpoint revision. Such a worker can finish skipped outstanding work with old weights or overwrite a repaired vector after the reembed command, so recomputing with the command's new settings does not establish the promised repaired corpus. Define the supported operational sequence or enforcement that prevents writers using the previous checkpoint from participating during and after repair, and state the limits of search correctness while one key contains old and new vectors. Carry that decision into the operator documentation task and verify it with distinct fake checkpoint outputs and an outstanding old-revision writer. No new provenance table is required if a clear, justified operational precondition suffices. | fixed |

### Validation

- HEAD and branch match the requested commit and `change/stretch-reembedding-tooling`; the working tree was clean before review.
- `scripts/pregate-verify.sh gate1 stretch-reembedding-tooling` passed, including strict OpenSpec validation, with zero warnings.
- Reviewed proposal, design, tasks, both delta specs, handoff, OpenSpec configuration, and the existing queue, runner, model cache and search contracts. The high risk tier is appropriate.

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-30
**Reviewed-Commit:** b77fd619caa62cd89e67fa08225871d291bcfa6e
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — Design decision 3 and the embedding-storage delta require both keys' existing transaction-scoped advisory locks in consistent key-name order. Task 3.2 covers opposite retirements in two sessions, and task 5.1 requires failing-input evidence for removing the lock. The upload explanation now correctly excludes assets with neither vector, and task 3.1 introduces an old-key vector after the fill to exercise the deleting statement's coverage guard. |
| 2 | confirmed — The proposal, indexing-jobs delta and task 2.2 explicitly preserve queue-only execution under INDEXING_RUNNER=worker, require reporting the configuration responsible, and cover both commands under both runner configurations. Design decision 3, the embedding-storage delta and task 3.1 refuse retirement while replacement work remains outstanding even if vector coverage is complete. |
| 3 | changes-requested — Decision 6 and task 2.1 now include selected outstanding work without double-queuing, preserve live claims and terminal-failure reset semantics, and plan pending-job recovery. However, decision 7 and task 2.3 refuse reembed while ANY work for that key is outstanding: after an inline reembed crashes with pending work or an expired running claim, its rerun must refuse before the recovery engine can execute that work. This contradicts the proposal's resume claim and the indexing-jobs recovery scenarios, and leaves the named no-worker recovery case unsupported. Reconcile checkpoint safety with recovery explicitly across proposal, design, specs and tasks. Also specify how a not-yet-due retry is reported without claiming completion, and add an execution regression for an expired claim with no worker; task 1.3 only tests that the query distinguishes live and expired claims. |
| 4 | changes-requested — Decision 7 supplies a justified operational precondition (change configuration, restart every writer, then repair), acknowledges invisible stale processes, and states mixed-checkpoint search limits; task 4.3 carries these into operator documentation. The requested verification is still absent: task 2.3 only tests a generic outstanding-work refusal, and its ordinary fake-embedder rebuild test does not require distinct checkpoint outputs or an outstanding old-revision writer. Add a verification task that exercises that writer and the supported restart/recovery sequence, demonstrates that final repaired vectors all come from the new fake checkpoint, and that an old claim cannot subsequently overwrite them. Keep this consistent with finding 3's interrupted-repair recovery rather than relying on a blanket refusal that prevents recovery. |

### Validation

- Reviewed only the diff from 95669971444978df7d672f6f41d4f224e2ac5f89 to b77fd619caa62cd89e67fa08225871d291bcfa6e and collateral contracts reachable from findings 1–4; no unrelated findings were introduced.
- Branch and HEAD match the request; the working tree was clean before confirmation. All four source findings were dispositioned as fixed, so confirmation was eligible.
- Checked the existing transaction-scoped queue lock, claim eligibility (including expired leases and available_at), finish_work reporting, runner configuration contract, process-local model cache and ADR-007 against current source.
- `scripts/pregate-verify.sh gate1 stretch-reembedding-tooling` passed, including strict OpenSpec validation, with zero warnings. `git diff --check` for the requested commit range passed.
- This is an artifacts-only Gate 1 confirmation; implementation tests and failing-input demonstrations remain future tasks. Only review.md was modified; no git write commands were run.
