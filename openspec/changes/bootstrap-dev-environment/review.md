# Review — bootstrap-dev-environment

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-20
**Reviewed-Commit:** a376a45650c88ac0299d1ef9ee808ae32655093d
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | blocker | `tasks.md` §4.5; `design.md` Decisions 6 and Goals | This high-tier change makes `make fmt-check` real by adding Ruff configuration, but the failing-input plan covers only `make lint` and `make types`. A clean positive run in task 3.1 does not satisfy the mandatory demonstrated failing input for every new or changed check. Add a temporary formatting violation that is accepted as valid Python, demonstrate that `make fmt-check` fails, restore it, and record the evidence. | fixed |
| 2 | blocker | `tasks.md` §6.1 and §§3–4 | The required `test:` commit for tasks 3–4 is not feasible as planned: those sections only run checks and explicitly restore/remove every temporary probe, leaving no persistent change for a normal commit. Reassign a persistent test artifact (for example task 1.3) to that commit, change the commit plan to attach the evidence to a commit that has a real diff, or explicitly design another feasible evidence record. | fixed |
| 3 | major | `proposal.md` Impact (`.github/workflows/ci.yml`); `design.md` Decision 9; `tasks.md` | The proposal permits an edit to `.github/workflows/ci.yml` if the branch run reveals one is needed, while the design assumes CI is unchanged and no task specifies, verifies, or provides a failing-input demonstration for such an edit. Because CI/verifier infrastructure is the stated high-risk trigger, this escape hatch would allow unreviewed scope after Gate 1. Either constrain this change to no workflow edit and require a scope/design update plus a new Gate 1 review if CI disproves the assumption, or design and task the possible workflow change now. | fixed |
| 4 | major | `tasks.md` §5.1 | The verification claim that every command in all three edited documents was run during tasks 1–4 is neither correctly ordered nor safely bounded: `cp .env.example .env && make init` is deferred to task 5.3, and the existing documents also contain unrelated commands including the destructive reset command. Limit the claim to commands added or changed by this change, name their exact executions and evidence, and place verification after any required user acceptance. | fixed |

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-20
**Reviewed-Commit:** 2f87c72cc9f1146269210defd8d5331ff0bbb16f
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — task 4.6 and the design's check table now give `make fmt-check` a valid-Python formatting probe, require `make lint` to accept it, require `make fmt-check` to reject it, and restore the tree. |
| 2 | confirmed — task 6.1 now assigns the persistent smoke test to the `test:` commit and assigns each remaining persistent artifact to a feasible commit whose body records the relevant probe evidence. |
| 3 | confirmed — the proposal, design decision 9, and task 5.5 consistently prohibit a workflow edit under this approval and require a blocked handoff, revised artifacts, and a new Gate 1 review before any such edit. |
| 4 | changes-requested — task 5.1's bounded list still omits `make revision MSG='…'`, although this change plans to document all four guarded targets in `docs/reference/commands.md` and task 2.1 runs that command. Name its exact execution and evidence alongside `make migrate`, `make run`, and `make test-integration` so the bounded verification claim covers every command this change adds or changes. |
