# Review — add-folder-indexing-cli

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-21
**Reviewed-Commit:** f010e59bdb05235e445da4ab513f776e6ad3e0e9
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | blocker | `design.md` decisions 2–3 and Risks; `specs/folder-indexing/spec.md` “The walk stays inside the folder it was given”; `tasks.md` 1.1 and 5.1–5.3 | The proposed `lstat`/`resolve` checks happen before the later path-based open, so an entry can be replaced in between with a FIFO or an outward symlink. The acknowledged changing-tree case therefore can violate both SHALL NOT guarantees by blocking or reading outside the tree. Specify a mechanism that binds validation to the object actually opened, and add a deterministic mutation-race test plus its required failing-input probe. | fixed |
| 2 | blocker | `design.md` decision 8; `tasks.md` 4.3 and 5.12; `specs/folder-indexing/spec.md` “An import ends with vectors, not with a backlog” | The existing `indexing.drain` claims an arbitrary global due batch and returns no count or identity. Repeating it a number of times bounded by assets created can consume older unrelated jobs while leaving this import’s jobs pending, contradicting the guarantee that the queued work for every imported asset is carried out. Define a feasible way to target or observe completion of this run’s job IDs, and test with a pre-existing due queue large enough to fill the bound. | fixed |
| 3 | major | `design.md` decisions 2–3; `tasks.md` 1.1 | The symlink policy is internally contradictory: decision 2 says a candidate exists only when `lstat` reports a regular file, while decision 3 says an in-tree symlink to a file is read. `lstat` reports that entry as a symlink, so both rules cannot be implemented. Choose whether all file symlinks are skipped or safe in-tree file symlinks are accepted, then align the proposal, spec, design, classification expectations, and probes. | fixed |
| 4 | major | `specs/folder-indexing/spec.md` lines 22–26 and 71–91; `tasks.md` 2.1 | The first acceptance scenario says the imported asset is indistinguishable from an upload except for `source`, but the same spec requires import-only relative-path metadata and task 2.1 expects that additional difference. Make the scenario’s equality claim match the required stored origin fields so the integration assertion has one unambiguous oracle. | fixed |
| 5 | major | `design.md` Applicability, “Empty / zero / null inputs”; `tasks.md` groups 1–5 | The applicability table claims defined, tested outcomes for an empty directory, no-candidate directory, zero-byte file, and a root directory that is itself a symlink, but the design never defines the root-symlink outcome and no task explicitly verifies these cases. This fails the Gate 1 requirement that every scope claim have implementation and verification coverage. Define the outcomes and add corresponding tasks/tests and failing-input probes for any new guards. | fixed |
| 6 | major | `specs/folder-indexing/spec.md` lines 136–148; `design.md` decision 8; `tasks.md` 4.3 | The indexing contract simultaneously says a failed job does not fail the import and remains under queue retry rules, while its success scenario and task 4.3 require every imported asset to have vectors when the command returns. A model failure cannot satisfy both. Define what the command guarantees and reports for retried or terminally failed jobs, and add verification for that path. | fixed |

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-21
**Reviewed-Commit:** 1f3d14549d03206a380923ee7f69fa4ce48c21cc
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — the descriptor-relative, non-blocking, no-follow open binds validation and reading to the opened object; tasks 1.4 and 6.3 provide the deterministic replacement race and failing-input probe. |
| 2 | confirmed — restricted claims by the imported assets, status observation, and the pre-existing-queue test make completion of this run's work independently observable and claimable. |
| 3 | confirmed — proposal, design, spec, tasks, and probes now consistently skip every file symlink, including one whose target remains inside the tree. |
| 4 | confirmed — the equality claim and task 2.1 now identify both intentional differences: `source` and the recorded-origin metadata. |
| 5 | confirmed — the root-symlink outcome is defined, and tasks 1.5, 1.6, and 2.5 explicitly verify empty/no-candidate directories, a symlinked root, and a zero-byte candidate. |
| 6 | changes-requested — the requirement now generally permits return with work still queued, but its plain “A folder is imported” scenario still unconditionally requires every created asset to have vectors. More importantly, decision 8 stops when a claim takes nothing; after a failed non-terminal attempt the existing queue applies backoff, so the next targeted claim takes nothing and the command returns with that job queued rather than exercising every permitted attempt. Task 4.4 nevertheless requires a job that fails every permitted attempt to be terminally failed and reported as such. Align the scenario and task with the actual queued-after-retry outcome, or define a feasible policy that waits/retries to terminal failure, then verify both the retriable and terminal paths. |
