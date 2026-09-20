---
name: "git:commit"
description: Analyze repo changes, generate a Conventional Commit message, get user approval, and commit. Use when the user wants to commit changes, asks to save work, or says /git:commit. Never pushes — commit only.
---

# Commit Command

Create a well-formed Conventional Commit for the current repository state.

## Critical: Command Execution

Permission patterns like `Bash(git *)` only match simple commands.
Compound commands (`git status && git diff`) trigger permission prompts
even when individual commands are allowed.

- Execute each command as a separate `Bash()` call — never chain with
  `&&`, `||`, `;`, or pipes
- Read-only git commands (status, diff, log) can run in parallel
- Write git commands (add, reset, commit) must run sequentially — they
  share the index and will race on `index.lock`

## Workflow Integration (AGENTS.md)

Check the current branch with `git branch --show-current`:

- On `change/<id>` — normal case, proceed.
- On `main` — direct commits to `main` are allowed only for baseline/doc
  fixes with explicit user consent. The user invoking this command on
  `main` counts as consent for the changes they select; still name the
  branch in the summary so the choice is conscious.
- Committing does not replace the session-end protocol — if this commit
  ends the session, run `/workflow:handoff` afterwards.

## Workflow

### Step 1: Preflight checks

1. `git status --short`
2. `git diff --name-only --diff-filter=U`
3. `test -f "$(git rev-parse --git-path MERGE_HEAD)"`
4. `test -d "$(git rev-parse --git-path rebase-merge)"`
5. `test -d "$(git rev-parse --git-path rebase-apply)"`
6. `test -f "$(git rev-parse --git-path CHERRY_PICK_HEAD)"`
7. `git rev-parse --verify HEAD`

Unresolved conflicts, or a merge/rebase/cherry-pick in progress → warn
and stop. No commits yet → initial commit, do not use `git reset HEAD`.

### Step 2: Gather repository state (read-only, parallel)

1. `git diff --stat` · 2. `git diff --cached --stat` ·
3. `git diff --name-only` · 4. `git diff --cached --name-only` ·
5. `git ls-files --others --exclude-standard` · 6. `git log --oneline -5`

### Step 3: Handle partially staged files

A file in both `git diff --name-only` and `git diff --cached --name-only`
is partially staged. Ask per file: preserve staged hunks only / stage
the whole file / exclude. For "preserve", never run `git add`,
`git reset`, `git restore --staged` or `git rm --cached` on that file.

### Step 4: Ask what to commit

```
**Branch:** change/<id>
**Staged:** …   **Unstaged:** …   **Untracked:** …

What to commit?
1. Everything   2. Tracked changes only   3. Staged only   4. Pick files
```

Never sweep in `.env`, credentials, IDE files or other changes' files —
call them out and leave them.

### Step 5: Granularity

Only if selected changes touch multiple unrelated areas, offer a split
with a suggested grouping. Cohesive changes — skip this question.

### Step 6: Generate the message

**Type**: `feat` · `fix` · `docs` · `style` · `refactor` · `test` ·
`chore` · `build` · `ci` · `perf` · `review` (gate records — normally
written by `scripts/gate-run.sh`, not by hand).

**Scope**: a short semantic label — the change id (shortened) when the
work lives in one change; the module/directory otherwise; omit for
three or more unrelated areas.

**Subject**: imperative mood, lowercase, no period, under 50 chars,
English.

**Body** (optional): when the change affects behavior, the diff is
large, or the reason is not obvious. Flag security-sensitive changes
(auth, money, payments, input handling, dependencies) explicitly.

**Trailer**: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
(or the acting agent's trailer).

### Step 7: Present and confirm

```
type(scope): subject

body

1. Commit   2. Edit   3. Cancel
```

### Step 8: Execute (sequential)

1. `git add <file>` per file (skip "preserve hunks" files).
2. `git commit --file -` with a quoted HEREDOC carrying the full message
   including the trailer.
3. `git status --short`, then `git log --oneline -1`.

**Never run `git push`.**

## Language

Commit messages are always in English. User-facing output follows
`.claude/rules/language.md` (Russian chat).
