---
name: "workflow:handoff"
description: Execute the strict session-end protocol for a change — reconcile tasks.md, validate, commit everything, update handoff.md. Use when a working session ends or the user says to wrap up.
argument-hint: [change-id] [target-state]
---

# Session Handoff

Executes the AGENTS.md Session-End Protocol (strict) as one flow. After
this command completes, no uncommitted work remains and `handoff.md`
reflects reality. One command per `Bash()` call; write commands
sequentially.

### Step 1: Determine the change

- Argument `$1` = change id, or derive from the current `change/<id>`
  branch. On `main` with no argument: if the session's work was
  main-level (docs/config with user consent), skip change-specific steps
  and just offer `/git:commit` for the remainder.
- With a resolved change id: verify branch `change/<id>` exists and
  **check it out before any write**. If checkout is impossible (dirty
  tree with unrelated work), stop and report instead of committing onto
  the wrong branch.

### Step 2: Reconcile tasks.md

Compare checkboxes against what was actually done (git log of the
branch + session context). Fix discrepancies in both directions. When
unsure whether an item is truly done, ask — never guess a checkbox into
`[x]`.

### Step 3: Validate

`openspec validate <id> --strict` — must pass. If it fails, fix the
artifact first; if the fix is impossible now, record it as the top
blocker and tell the user explicitly.

### Step 4: Commit all work

- Commit uncommitted work to the change branch using the `/git:commit`
  conventions. Split into cohesive commits if areas are unrelated.
- Commit only change-scoped files. Unrelated or unexpected files
  (secrets, editor artifacts, other changes' files) are NOT swept in —
  list them to the user and leave them untracked.
- If work is genuinely unfinishable, a `blocked` handoff naming the
  blocker is a legal session end.

### Step 5: Update handoff.md

Overwrite `openspec/changes/<id>/handoff.md` per the AGENTS.md format.
Target state `$2` if given, else derive from the lifecycle. Commit it
(`chore(<id>): session handoff`).

### Step 5a: Gate handoffs

If the target State is `awaiting-gate-1` or `awaiting-gate-2`: confirm
the Definition of Ready in AGENTS.md is complete for the tier, then run
`scripts/pregate-verify.sh <gate1|gate2> <id>`. Non-zero exit → the
handoff may NOT set the awaiting state: fix the failures first, or
record `blocked` naming them.

### Step 5b: Reconcile the roadmap

If the plan changed this session (a planned change was added, renamed,
reordered, completed, or its scope shifted), update
`openspec/ROADMAP.md` and include it in the handoff commit. If the plan
did not change, touch nothing.

### Step 6: Confirm

`git status --short` must be empty. Report: state recorded, next step,
blockers. If the state is `awaiting-gate-1/2`: in review mode `auto`
remind that the review is triggered with `/gate-review <id> <gate>`; in
`manual` say plainly that the iteration is done and the user's Codex
review is the next step (`/gate-review <id> <gate> request` prints the
prompt if it was not printed yet; afterwards `/gate-review <id> <gate>
record`).

Repository content in English; user-facing output in Russian.
