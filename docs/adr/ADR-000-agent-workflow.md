# ADR-000: Agent Workflow

**Date:** 2026-09-08
**Status:** accepted
**Scope:** how Claude Code and Codex work on SemanticShelf

Numbered 000 as a process decision, preceding the architectural series
(ADR-001…). Adapted from the narrative-forge multi-agent workflow
(ADR-000, ADR-015, ADR-023, ADR-080, ADR-096, ADR-097 of that
repository) and its two external critiques, which measured 470 review
rounds over 43 changes — 10.9 per change, 75% of them induced by
earlier fixes — and concluded that the process had become
over-controlled. This ADR keeps what earned its cost and drops what did
not.

## Problem

Two agents (Claude Code, Codex) and one human work on the repository.
Without an explicit protocol there are no roles, no review discipline,
no state between sessions, and no guarantee that either agent reads the
rules the other relies on. A pet project also has one developer and a
limited budget: every mandatory step must pay for itself.

## Decisions

1. **Roles.** Claude Code executes (explores, proposes, implements,
   verifies). Codex reviews independently at the gates a change's risk
   tier requires. The user is the final arbiter, the only party who
   merges to `main` and the only party who pushes.
2. **Unit of work.** One OpenSpec change on branch `change/<id>`. Every
   multi-task effort is a change; plans live in `tasks.md` and
   `openspec/ROADMAP.md`, never only in agent memory.
3. **Risk tiers decide review depth.** `low`: no external review.
   `medium`: Gate 2 (code). `high` (auth, money, payments,
   concurrency, deletion, external effects, security-sensitive input,
   verifier infrastructure): Gate 1 (artifacts) + Gate 2 + a failing
   input for every new check. Uniform rigor is not uniform assurance —
   it is uniform cost.
4. **Review record in the repository.** `review.md` beside the change:
   append-only rounds, confirmations and waivers, each bound to the
   commit it reviewed. The LAST record of a gate decides. Gate 2 has a
   freshness rule (only protocol files may change after the reviewed
   commit); Gate 1 has none, so describing an implementation in the
   design never reopens planning review — only a real scope change does.
5. **Confirmation, not re-review.** After a `changes-requested` round the
   executor fixes the CLAIM (sweeps every sibling artifact) and requests a
   scoped confirmation of the named findings. Two failed confirmations on
   the same finding stop the loop: split, reduce, or ask the user.
6. **Pull, not push.** The reviewer receives identifiers only and gathers
   context itself. The prompts are constants in `scripts/gate-run.sh`;
   the executor cannot add hints. The sandbox cannot commit; the runner
   verifies and commits with a Codex co-author trailer.
7. **The runner is the only path to the reviewer.** `scripts/gate-run.sh`
   performs the mechanical floor (`scripts/pregate-verify.sh`: strict
   validation, whitespace, tier and non-goals declared, tasks and paths
   consistent, `make check` green at Gate 2) and the invocation in one
   process, so a failing floor can never reach the reviewer.
8. **Two review modes, one runner.** `**Review mode:**` in AGENTS.md
   selects `auto` (the runner invokes Codex headlessly) or `manual`
   (the runner prints the constant prompt after the floor; the user runs
   Codex; the runner later verifies and commits the record exactly as in
   `auto`). Manual mode exists because the reviewer's subscription may be
   metered separately from the executor's; it changes who presses the
   button, not what is verified. The executor never writes into
   `review.md` in either mode.
9. **Session-end protocol.** Tasks reconciled, strict validation,
   everything committed, `handoff.md` current, roadmap reconciled. A
   `blocked` handoff naming the blocker is a legal session end; leaving
   work uncommitted is not.
10. **Encoding.** Everything critical lives in files that reach agent
   context automatically: `AGENTS.md` (imported by `CLAUDE.md`, read
   natively by Codex), `.claude/rules/`, `openspec/config.yaml`.
   Mechanical enforcement lives in `scripts/`; slash commands are thin
   wrappers that reference AGENTS.md rather than restating it.
11. **Process changes need portfolio evidence and a named removal.** A
    new rule, check or ADR is adopted only when the same defect appeared
    in several distinct changes and the proposal names the manual step it
    retires. One-off incidents are fixed, not legislated.

## Deliberately NOT adopted from the source workflow

- Typed post-decision change classification, state-repair records,
  closure manifests, invocation telemetry, generated documentation
  projections, claim-impact queries, a supersession index. Each was
  justified there by a corpus of 85 changes and its own measured defect
  classes; none has evidence here yet. Adopt one only under decision 11.
- Mandatory internal (same-model) pre-review rounds — measured there as
  cost without independence.
- Two gates for every change regardless of risk.

## Consequences

- Review cost scales with risk; a docs fix costs no reviewer round.
- Independence of the review is a property of the script, not of the
  executor's restraint.
- The record of every decision, finding and handoff is in git and
  readable without any external service.
- Prompt-level contracts (OpenSpec operation guidance, command text)
  are not mechanically enforced; the verifier scripts and CI are the
  floor, and the user's merge is the ceiling.

## Verification

`scripts/workflow_verify_test.sh` and `scripts/gate_run_test.sh` demonstrate
every verifier and runner rule with a failing input (the reviewer is a
stub on PATH); CI runs every `scripts/*_test.sh` by glob, strict OpenSpec
validation and `make check`.
