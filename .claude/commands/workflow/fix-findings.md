---
name: "workflow:fix-findings"
description: Address open findings of the latest review round, update their Status, commit, and request a scoped confirmation.
argument-hint: [change-id]
---

# Fix Findings

Executor-side counterpart of `/gate-review`: work through the open
findings of the latest review round, then send the change back for
confirmation. Follows the AGENTS.md Review Protocol.

### Step 1: Locate the work

- Argument `$1` = change id, or derive from the current `change/<id>`
  branch. Check out `change/<id>` if not already on it.
- Read `openspec/changes/<id>/review.md`; take the **latest round** for
  the gate in progress. If its verdict is `approved`/`confirmed` or no
  finding is `open` — report that and stop.

### Step 2: Work through findings

For each finding, in severity order (`blocker` → `major` → `minor`):

1. Re-read the cited location; verify the finding against current state
   (it may already be stale).
2. `blocker` / `major`: fix it, or — if you disagree — set
   `wont-fix (+reason)`. For `major`, explicit user acceptance is
   required: ask before marking `wont-fix`.
3. `minor`: fix or decline at your discretion; record the decision
   either way.
4. Update the finding's Status cell in `review.md`. Never edit the
   reviewer's Finding text.

### Step 3: Fix the claim, not the line

After each fix, state the INVARIANT the finding violated and re-attack
the whole thread:

- **Overclaimed guarantee** → walk every failure state of the mechanism,
  not just the named case.
- **Incompleteness** → rebuild the ENTIRE set from its source, never add
  only the member the reviewer named.
- **Inconsistency** → `rg` the whole repository for the affected term
  (spec, design, tasks, docs, tests, README) and reconcile every hit.
- **Untested rule** → add the test that fails when the rule is removed.

Note in the commit body which sibling artifacts were checked.

### Step 4: Validate and commit

1. `make check` (Gate 2) / `openspec validate <id> --strict` (both).
2. Commit fixes in cohesive commits (Conventional Commits, English,
   agent trailer); include the `review.md` Status updates.

### Step 5: Request confirmation

1. Update `handoff.md`: State back to `awaiting-gate-<N>`, note what
   was fixed.
2. Review mode `auto`: run `/gate-review <id> <N> confirm <round>`.
   Review mode `manual`: run `/gate-review <id> <N> request <round>`,
   report "review needed" with the printed prompt, and end the turn —
   the user runs Codex; next session `/gate-review <id> <N> record`.
3. If this is the second failed confirmation on the same finding, stop
   and ask the user to split, reduce, or arbitrate — do not loop.

Repository content in English; user-facing output in Russian.
