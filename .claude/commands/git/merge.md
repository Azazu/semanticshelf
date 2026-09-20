---
name: "git:merge"
description: Merge a reviewed change branch into main after the workflow verifier passes. User-triggered only. Never pushes, never deletes branches without confirmation.
argument-hint: [change-id]
---

# Merge Command

Merge `change/<id>` into `main` per the AGENTS.md lifecycle. Merging
into `main` is the user's decision — run this flow only when the user
invoked this command. One command per `Bash()` call; no chaining.

### Step 1: Determine the change branch

- `$1` = change id → branch `change/$1`.
- Without argument: the current `change/*` branch, else
  `git branch --list 'change/*'` and ask the user to pick.

### Step 2: Git preflight

1. `git status --short` — working tree must be clean; otherwise stop and
   suggest `/git:commit`
2. `git rev-parse --git-path` probes for MERGE_HEAD / rebase-merge /
   rebase-apply / CHERRY_PICK_HEAD — any hit → warn and stop
3. `git rev-parse --verify change/<id>` — branch must exist
4. `git log main..change/<id> --oneline` — must be non-empty
5. `git merge-base --is-ancestor main change/<id>` — if this fails the
   branch is behind `main`: stop; the executor incorporates `main` on
   the change branch first (then Gate 2 is confirmed again if the code
   diff changed)

### Step 3: Verify the workflow

Run the exact invocation `scripts/workflow-verify.sh merge <id>`. It
reads the change files **from the branch ref**, so running from `main`
can never validate the wrong copies. It checks: tasks all `[x]`;
`handoff.md` State `ready-to-merge`; for tier `medium`/`high` the last
Gate 2 record is `approved`/`confirmed`/`waived` and fresh (only
`review.md`, `handoff.md`, `tasks.md` differ since its
`Reviewed-Commit`); no finding row left `open`; strict validation.

Any FAIL → name the exact failed condition and stop. Only the gate
VERDICT may be waived by the user (a `## Waiver · Gate 2` block in
`review.md`, committed on the change branch). Open findings,
incomplete tasks, wrong handoff state and validation failures are
never overridable — fix them on the change branch.

### Step 4: Confirm

```
**Merge:** change/<id> → main
**Commits:** <n> (--oneline list)
**Tier:** medium · **Gate 2:** approved (round <n>, <date>) | waived by user | n/a (low)
**Checks:** make check green · validation strict OK

1. Merge   2. Cancel
```

### Step 5: Execute (sequential)

1. `git checkout change/<id>`, then `openspec validate <id> --strict`
   and `make check` — both must pass (never waivable)
2. `git checkout main`
3. `git merge --no-ff change/<id> -m "merge: <id> (gate 2 approved)"`
   (variants: `(gate 2 waived)`, `(tier low, no gate)`)
4. `git status --short`; `git log --oneline -3`
5. Conflicts → do not resolve silently: show the files and ask;
   `git merge --abort` is the safe default

### Step 6: After the merge

Offer, do not perform unprompted:
1. Update `handoff.md` State to `merged` and `/opsx:archive <id>`
   (the archive commit on `main` needs explicit user confirmation)
2. `git branch -d change/<id>` — only on explicit confirmation

**Never run `git push`.**

Merge commit messages are English; user-facing output in Russian.
