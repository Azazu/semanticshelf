# Review — harden-quality-and-docs

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** b9fe520c2ffda98bdb038c7156770136a9968299
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `proposal.md:3-12`; `.github/workflows/ci.yml:105-112`; `AGENTS.md` Risk tiers | This change adds a mandatory dependency-audit step to CI. `AGENTS.md` explicitly assigns verifier/CI infrastructure to `high`, but the proposal declares `medium` and skipped Gate 1. Raise the tier and reconcile the required Gate 1 review before treating this change as merge-ready. | fixed |
| 2 | major | `app/schemas/jobs.py:76-116`; `tests/api/test_openapi_examples.py:70-87,142-154` | The published `GET /api/v1/assets/{asset_id}/jobs` example drops `lease_expires_at` and `last_error` from each job because FastAPI encodes `responses=` with `exclude_none`. Both fields are required, though nullable, in `IndexingJobRead`. Validating the example extracted from `create_app().openapi()` with `IndexingJobList.model_validate` produces four missing-field errors. The test validates the original constant and deliberately strips its nulls for document comparison, so it misses the invalid example and the delta spec's requirement that the published example parse as the answer. | fixed |
| 3 | major | `tests/unit/test_layering.py:114-121,166-181` | The router SQL guard examines only `ast.ImportFrom`. A router can add `import sqlalchemy as sa` and call `sa.select(...)` without the guard seeing it; the general forbidden-edge table also has no router-to-`sqlalchemy` rule. Thus the new test does not enforce NFR-QA-2's "routers contain no SQL" promise. Cover direct package imports and demonstrate the check failing on that form. | fixed |
| 4 | major | `Makefile:82-86`; `docs/explanation/requirements.md:278`; `openspec/changes/harden-quality-and-docs/specs/deployment/spec.md` | The normative NFR-SEC-6 requires CI to fail on known HIGH/CRITICAL advisories with a fix. `make audit` runs plain `uv audit --locked`, which has no severity or fix-availability filter here, while the delta spec silently broadens the failure condition to any fixable vulnerability. Reconcile the normative requirement, delta spec, and implemented failure policy; demonstrate the chosen policy on a failing input. | fixed |

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** c16f82c13123a6631ed7c76e1543e34ca70aec8e
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `proposal.md:98-110`; `design.md:45-48,181-183`; `app/core/openapi.py` | The proposal says service behaviour is unchanged and that the only Python changes are schema examples and tests. The change also modifies OpenAPI generation in `app/core/openapi.py` and its installation in `app/main.py` to restore nullable fields in the served document. This is a change to the service's published output and a new implementation mechanism for the delta spec's example guarantee. State that scope and mechanism accurately in the proposal and design so Gate 1 reviews the change actually being made. | fixed |
| 2 | major | `tasks.md:31-35,88-95,139-142`; `handoff.md:59-65`; branch status | Tasks 1.3, 3.2 and 5.3 are checked even though their verification requires a pushed branch, green CI and the user's report that GitHub rendered the Mermaid diagram. The handoff still asks the user to push and check the diagram, and this branch is ahead of its remote. Record only completed evidence as done; leave the pending external verification open until it occurs. Checked tasks must have evidence, and each task must be feasible at its lifecycle point. | fixed |

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** b3155879ce8afe43eb35700875f08eb4d293d8bf
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — `proposal.md` now names the change to the published OpenAPI document and the `app/core/openapi.py` / `app/main.py` mechanism; `design.md` explains why and how declared examples are restored after encoding. |
| 2 | changes-requested — Tasks 1.3 and 5.3 are open pending CI on the reviewed head, and task 3.2 records a user report for the unchanged README. But `handoff.md` still asks the user to check the Mermaid rendering, contradicting that recorded evidence. Reconcile the handoff with the task before treating 3.2 as verified. |

## Confirmation 2 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** a16976bfc3c8456701d6f9c64f5526b46e54138b
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — The proposal and design still state that `app/core/openapi.py` changes the published OpenAPI document and explain the mechanism. |
| 2 | changes-requested — `handoff.md` now agrees with task 3.2 that the unchanged README's Mermaid rendering was already reported by the user, and tasks 1.3 and 5.3 remain open pending CI on the current head. However, task 5.1 is still checked and says "every task above is checked with its evidence" while 1.3 above it is open. Leave 5.1 open or revise its completion condition so checked tasks state only completed evidence. |

## Confirmation 3 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** 7a0aee1c8b4596eb59710c8c46d2ccc937937b95
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — `proposal.md` and `design.md` accurately describe the published OpenAPI document change and the mechanism in `app/core/openapi.py` and `app/main.py`. |
| 2 | changes-requested — Task 5.1 is now open alongside 1.3 and 5.3, so its completion claim no longer precedes its evidence. But `handoff.md` lines 55–58 still call 1.3 and 5.3 "the only two still open". Reconcile the handoff with the three open tasks before confirming the evidence record. |

## Confirmation 4 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** ff145a3eb047881d781f977941414546b45d88f9
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — `proposal.md` and `design.md` identify the change to the published OpenAPI document and explain how `app/core/openapi.py` restores the declared examples after FastAPI encoding. |
| 2 | changes-requested — Tasks 1.3 and 3.2 now cite the reported CI run and Mermaid rendering. But task 5.3 is checked despite requiring green CI on the exact HEAD: the reported run was on `b17653e`, while the reviewed HEAD is `ff145a3`, which is still ahead of the remote. `handoff.md` likewise says another push and green run are needed. Task 5.1's claim that every preceding task has its evidence therefore still depends on an unverified 5.3. Leave 5.3 and 5.1 open until that evidence exists, then reconcile the handoff. |
