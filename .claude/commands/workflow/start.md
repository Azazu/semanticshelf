---
name: "workflow:start"
description: Start a new OpenSpec change — create branch change/<id> from main, scaffold the change, write the initial handoff. Use before /opsx:propose.
argument-hint: <change-id> [one-line description]
---

# Start a change

Everything after this command happens on `change/<id>` (AGENTS.md, Git
Conventions). One command per `Bash()` call; no chaining.

1. **Preflight** (read-only, parallel): `git status --short` must be
   empty (otherwise stop and suggest `/git:commit` or a stash);
   `git branch --show-current` — note where we are; `openspec list`.
   If `openspec/changes/$1` or branch `change/$1` already exists, stop
   and report — use `/workflow:status` instead.
2. **Branch**: `git checkout main`, then `git checkout -b change/$1`.
3. **Scaffold**: `openspec new change "$1"` (never create the directory
   by hand — the CLI writes `.openspec.yaml`).
4. **Handoff**: write `openspec/changes/$1/handoff.md` per the AGENTS.md
   format with `**State:** proposing`, today's date, `claude`, and the
   one-line description (if given) under "Next step: /opsx:propose".
5. **Roadmap**: if `openspec/ROADMAP.md` lists this change, leave it; if
   the change is new to the plan, add a row (ADR-000: plans are
   repository-visible).
6. **Commit**: `chore(<id>): start change` with the agent trailer.
7. Report the branch and say: "Дальше — `/opsx:propose <id>`".

Repository content in English; user-facing output in Russian.
