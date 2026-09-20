---
name: "workflow:status"
description: Show the state of all OpenSpec changes — branch, handoff state, gate verdicts, open findings, task progress, uncommitted work. Read-only. Use at session start or when the user asks where things stand.
---

# Workflow Status

Read-only panorama of the agent workflow (AGENTS.md). Never modifies
anything.

## Steps

### Step 1: Gather (read-only, parallel where possible)

1. `git branch --show-current`
2. `git status --short`
3. `git branch --list 'change/*'`
4. `openspec list`

### Step 2: Per change (every directory in `openspec/changes/`, excluding `archive/`)

For each change `<id>`, read:

1. `proposal.md` → `**Risk-Tier:**` (missing → flag it)
2. `handoff.md` → **State**, last updated, by whom (missing → state unknown, flag it)
3. `review.md` → last decision record per gate
   (`scripts/workflow-verify.sh decision openspec/changes/<id>/review.md <gate>`),
   count of finding rows still `open`
4. `tasks.md` → checked vs total checkboxes (`- [x]` vs `- [ ]`)
5. Branch `change/<id>` exists? `git log main..change/<id> --oneline | wc -l` commits ahead

### Step 3: Report

Compact table, then a next-step line per change derived from the
AGENTS.md lifecycle and the risk tier:

```
| Change | Tier | State | Gate 1 | Gate 2 | Tasks | Branch (ahead) |
|---|---|---|---|---|---|---|
| add-recipe-crud | medium | implementing | n/a | — | 3/9 | change/… (+4) |
```

- **Next step** examples: "fix open Gate 2 findings (`/workflow:fix-findings`)",
  "manual review mode: waiting for the user's Codex review, then
  `/gate-review <id> 2 record`" (state `awaiting-gate-2` with no record
  bound to HEAD),
  "implementation may start", "ready for `/git:merge`", "tier low — no
  gate, run `make check` and hand off to ready-to-merge".
- Flag inconsistencies explicitly: uncommitted files on a change branch,
  handoff state contradicting review verdicts, checked tasks without
  commits, a change with no handoff.md, a `high` tier without a Gate 1
  record.
- If the working tree is dirty, say so first — it violates the
  session-end protocol.
- If there are no active changes, read `openspec/ROADMAP.md` and report
  the next planned change, so the session starts with a concrete next
  step. If the roadmap lists nothing, say exactly that.

Output in Russian (user-facing), per `.claude/rules/language.md`.
