---
description: Run a Codex gate review (full) or a scoped finding confirmation for an OpenSpec change; in manual review mode, request or record it
argument-hint: <change-id> <gate: 1|2> [full|confirm <source-round>|request [<source-round>]|record]
---

Wrapper over the gate runner. The runner — not this file — is the
procedure: it performs the mechanical floor and the reviewer step in
one process, so nothing here may reorder, skip or substitute a step.

First read the review mode: `scripts/workflow-verify.sh mode` → `auto`
or `manual` (the `**Review mode:**` line in AGENTS.md).

## auto

Run exactly one of:

```bash
scripts/gate-run.sh "$1" "$2" full
scripts/gate-run.sh "$1" "$2" confirm "$4"
```

Pass no other argument: the prompts are constants inside the runner and
extra arguments are refused rather than appended.

## manual

Never invoke `codex` yourself in this mode — the user runs it.

1. **Request** (no third argument, or `request [<source-round>]`):

   ```bash
   scripts/gate-run.sh "$1" "$2" request        # full round
   scripts/gate-run.sh "$1" "$2" request "$4"   # confirmation of round $4
   ```

   On exit 0: update `handoff.md` to `awaiting-gate-$2` with Next step
   `scripts/gate-run.sh $1 $2 record`, commit it (`chore(<id>): request
   gate $2 review`), then report to the user in Russian: the iteration is
   done, review is needed — gate, change id, commit, and the printed
   prompt block verbatim. **End the turn.** Do not poll, do not wait,
   do not write anything into `review.md`.

2. **Record** (`record`, next session, after the user says the review
   is done):

   ```bash
   scripts/gate-run.sh "$1" "$2" record
   ```

## Exit status (both modes)

- **0** — `full`/`confirm`/`record`: the record is verified and
  committed. Report the verdict and the findings summary; update
  `handoff.md` to the state the verdict implies (AGENTS.md lifecycle):
  approved/confirmed at Gate 1 → `implementing`; at Gate 2 →
  `ready-to-merge`; changes-requested → `fixing-g1` / `fixing-g2`.
  `request`: the prompt was printed — follow the manual step 1 above.
- **3** — another run holds the lock; report the owner it named and stop.
- **1 or 2** — the gate is NOT passed. Nothing was committed; report the
  runner's message. If `review.md` was left modified, show it to the
  user for inspection — do not commit it by hand and do not complete
  the reviewer's record yourself.

User-facing output in Russian (`.claude/rules/language.md`).
