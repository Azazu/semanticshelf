# Repository Guidelines — SemanticShelf

Single source of truth for how AI agents (Claude Code, Codex) work in
this repository. Both agents load this file automatically; when in
doubt it wins over default agent behavior. Process record:
`docs/adr/ADR-000-agent-workflow.md`.

Semantic search over images: CLIP text→image and DINOv2 image→image embeddings in PostgreSQL + pgvector, served by FastAPI.

**Review mode:** auto

## Agent Roles

| Agent | Role |
|---|---|
| Claude Code | Executor: explores, authors OpenSpec proposals/designs/tasks, implements, runs checks |
| Codex | Independent reviewer at the gates a change's risk tier requires; does not implement |
| User | Final arbiter; the only party who merges to `main` and pushes (branches before Gate 2, `main` after merge); in `manual` review mode also the party who runs Codex |

The `**Review mode:**` line above is read by `scripts/gate-run.sh`
(`auto` when absent). `auto`: the runner invokes Codex itself.
`manual`: the executor stops at every gate with a printed review
request, the user runs Codex by hand, and the executor records the
result next session. Switching modes is editing that one line.

## Change Lifecycle

Unit of work: one OpenSpec change on branch `change/<id>`. Every
multi-task effort — feature, refactor, tooling, docs — is a change; no
work happens outside one. Plans live in the change's `tasks.md` and in
`openspec/ROADMAP.md`, never only in agent memory.

```text
Claude  /workflow:start <id>      → branch change/<id>, handoff: proposing
Claude  /opsx:propose             → proposal, specs delta, design, tasks
        (high tier)  /gate-review <id> 1   → Codex Gate 1 on the artifacts
Claude  /opsx:apply               → implement, commit per logical block
Claude  make check                → lint + static analysis + tests, all green
User    git push -u origin change/<id> → CI green on the exact HEAD (medium/high)
        (medium/high) /gate-review <id> 2  → Codex Gate 2 on the code diff
Claude  /workflow:fix-findings    → fix, update Status, re-review (confirm)
        (manual mode) every /gate-review is two steps: `request` — the
        executor stops and reports "review needed"; the user runs Codex;
        `record` — the executor verifies and commits the record
User    /git:merge <id>           → merge --no-ff into main (verifier passes)
Claude  /opsx:archive             → specs synced, change archived
```

### Risk tiers (declared in `proposal.md` as `**Risk-Tier:** low|medium|high`)

| Tier | Covers | Review required |
|---|---|---|
| `low` | docs, comments, config wiring, tests-only, refactor with no behavior change | none — self-check + CI |
| `medium` | ordinary feature or behavior change | Gate 2 (code review) |
| `high` | auth/authorization, money and rounding, payments/webhooks, stock or any concurrency, deletion or irreversible migrations, external side effects, security-sensitive input handling, verifier/CI infrastructure | Gate 1 + Gate 2, plus a demonstrated failing input for every new check |

The user may raise a tier at any time. A reviewer who thinks a tier is
too low says so as a `major` finding.

- **Gate 1** — after proposal/design/spec/tasks exist, before implementation.
- **Gate 2** — after implementation, before merge and archive.
- A gate passes when the LAST decision record for that gate in
  `review.md` reads `approved`, `confirmed`, or `waived`.
- Gate 2 freshness: at merge time, nothing but `review.md`,
  `handoff.md` and `tasks.md` may differ between the Gate 2
  `Reviewed-Commit` and the branch head (`scripts/workflow-verify.sh
  merge <id>` checks this). Gate 1 has no freshness rule: design/task
  edits that merely describe the implementation do not reopen it;
  only a change of scope, requirements or architecture does — then
  the executor requests Gate 1 again.
- A user may waive a gate verdict (block format below). Waivers never
  cover task completion, strict validation, green checks or branch
  hygiene — those are fixed, not waived.

## Review Protocol

Review state lives in `openspec/changes/<id>/review.md`, append-only.
Three record kinds, one ordered stream per gate:

```markdown
# Review — <change-id>

## Round <n> · Gate <1|2>
**Reviewer:** codex
**Date:** YYYY-MM-DD
**Reviewed-Commit:** <sha of the change branch HEAD under review>
**Verdict:** approved | changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | blocker | file/section | description | open |

## Confirmation <n> · Gate <1|2> · Round <source-round>
**Reviewer:** codex
**Date:** YYYY-MM-DD
**Reviewed-Commit:** <HEAD reviewed>
**Verdict:** confirmed | changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed |

## Waiver · Gate <1|2>
**Granted-by:** user
**Date:** YYYY-MM-DD
**Commit:** <sha of the change branch HEAD being waived>
**Verdict:** waived
```

Severities: `blocker` — must be fixed before the gate passes; `major` —
fix, or obtain explicit user acceptance; `minor` — executor's
discretion. The executor updates finding Status (`open` → `fixed` or
`wont-fix (+reason)`) and never edits Finding text. If the reviewer
maintains an objection against a `wont-fix`, the user decides.

A **confirmation** reviews only the diff since the source round and the
named findings; it introduces no unrelated minor findings. After two
failed confirmations on the same finding, stop: split or reduce the
change, or ask the user to arbitrate — do not loop.

Fix the CLAIM, not the line: when a finding is fixed, `rg` the whole
repository for the term or rule it touched (spec, design, tasks, docs,
tests) so the old statement does not survive in a sibling artifact.
This was the single most expensive defect class in the process this
workflow descends from.

## Review Invocation

`scripts/gate-run.sh` IS the invocation; `/gate-review` is a thin
wrapper. It reads the review mode from this file and refuses the
operations of the other mode.

| Mode | Operations | What the runner does |
|---|---|---|
| `auto` | `<id> <gate> full` · `<id> <gate> confirm <round>` | lock, repository validation, the mechanical floor (`scripts/pregate-verify.sh`), the bounded hermetic Codex call, verification of the reviewer's output, commit of `review.md` |
| `manual` | `<id> <gate> request [<round>]` | lock, validation, the floor, then PRINTS the prompt (identifiers only) and stops; nothing is written or committed. The executor reports "review needed: gate N, commit X" to the user and ends the turn |
| `manual` | `<id> <gate> record` | after the user ran Codex: verifies that only `review.md` changed, that the last record is a Round/Confirmation for the gate bound to the current HEAD with a valid verdict, then commits it |

Between `request` and `record` nothing may be committed on the branch:
the record must bind to the commit that was requested. The user hands
Codex the printed prompt verbatim (interactive `codex` in the
repository, or the printed `codex exec` one-liner) and lets it write
`review.md` only.

- **Pull, not push.** The prompts are constants inside the runner and
  carry identifiers only. Codex gathers context itself: this file, the
  change artifacts, `openspec/config.yaml`, and for Gate 2
  `git diff main...change/<id>`. No summary, hint or focus area reaches
  the prompt — that is the independence guarantee of the review. In
  manual mode the same holds: the user passes the prompt unchanged.
- **Sandbox cannot commit — the runner does.** Codex runs with
  `-s workspace-write --ignore-user-config`; it writes only `review.md`.
- **A confirmation is refused while any finding of its source round is
  still `open`** — disposition every row first (`/workflow:fix-findings`).
- **Failure is fail-closed.** Timeout, non-zero exit, an unexpected
  modified file, or a record not bound to the reviewed commit → the gate
  is NOT passed, nothing is committed, `review.md` is left modified for
  inspection. The executor never completes or edits a reviewer's record.
- **Reviewer quota.** Codex's usage limits are far below the executor's.
  When a run fails on a quota or rate limit (non-zero exit with the
  limit named in the runner's log tail), the executor stops: it writes a
  `blocked` handoff naming the limit, tells the user, and ends the
  session. It never retries in a loop and never substitutes its own
  review for the reviewer's.
- Quick, record-less alternative for a sanity pass (not a gate):
  `codex exec review --base main`.

## Handoff Protocol

`openspec/changes/<id>/handoff.md`, overwritten at each session end:

```markdown
# Handoff — <change-id>

**Updated:** YYYY-MM-DD · <agent>
**State:** proposing | awaiting-gate-1 | fixing-g1 | implementing |
awaiting-gate-2 | fixing-g2 | ready-to-merge | merged | archived | blocked
**Branch:** change/<id>

## Done this session
## Next step
## Blockers
```

`blocked` is legal from any state and must name the blocker. In manual
review mode `awaiting-gate-1/2` also means "review requested, the user
runs Codex next"; the handoff's Next step names the exact
`scripts/gate-run.sh <id> <gate> record` call.

## Definition of Ready

A gate is requested only when the executor's own checks are done — the
reviewer's job is unknown weaknesses, not the executor's missing steps.

- **Before Gate 1:** `proposal.md` has `**Risk-Tier:**` and a
  `## Non-goals` section; every scope claim has an implementation task
  AND a verification task in `tasks.md`; each task is feasible at its
  lifecycle point. For `high` tier, `design.md` carries a short
  applicability table covering only the triggered questions: crash
  before/after an external effect, concurrent writers, money rounding,
  empty/zero/null inputs, authorization boundary, deletion/expiry,
  idempotency of retries. Non-applicable rows get one `n/a` line.
- **Before Gate 2:** `make check` green; every checked task has evidence
  (test, diff, or rendered output); every documented command was run in
  its exact form; every changed document re-read whole after the last
  edit; for `high` tier every new or changed check has a demonstrated
  failing input (a test that fails when the guard is removed); the user
  has pushed the branch and the CI run on the exact HEAD is green. The
  executor never queries GitHub Actions: the user watches the run and
  reports a failure, which is fixed before the gate. Prevention is the
  executor's duty: before asking for a push it runs locally every check
  CI runs (`openspec validate --all --strict`, every `scripts/*_test.sh`,
  `sh -n` over `scripts/*.sh`, `make check`, the integration suite when
  the database is up).
- **Mechanical floor:** `scripts/pregate-verify.sh <gate1|gate2> <id>`
  — run by `/gate-review` before the reviewer (FAIL aborts) and by
  `/workflow:handoff` when targeting `awaiting-gate-1/2`.

## Git Conventions

- Branch per change: `change/<id>`; never implement on `main`.
- Direct commits to `main`: only baseline/doc fixes with explicit user
  consent, plus the user-confirmed post-merge archive commit.
- Conventional Commits, English, imperative mood (`feat:`, `fix:`,
  `docs:`, `test:`, `refactor:`, `chore:`, `ci:`, `review:`).
- Commit per logical task block; small commits — the history is read.
- Commits carry no agent trailers (`Co-Authored-By` or similar) and no
  other authorship marks: the repository is a public portfolio and its
  contributor graph shows the developer only.
- Merging into `main` is the user's action (`/git:merge` executes it on
  the user's behalf after the verifier passes).
- **Agents never push, force-push, rebase shared history, or delete
  files/branches without explicit confirmation.**

## Session-End Protocol (strict)

Before ending any working session:

1. Update `tasks.md` checkboxes to actual state.
2. Run `openspec validate <id> --strict` — must pass.
3. Commit all change-scoped work to the change branch. No uncommitted
   work is left between sessions. Unrelated files are not swept in.
4. Update `handoff.md` (state, done this session, next step, blockers).
5. Reconcile `openspec/ROADMAP.md` if the plan changed.
6. If handing off into `awaiting-gate-1/2`: `scripts/pregate-verify.sh`
   passes for the target gate.

If completing the protocol is impossible, a `blocked` handoff naming
the blocker is the legal fallback — never silently abandon a session.
`/workflow:handoff` executes this protocol as one flow.

## Verification Rules (all agents)

Verify against the current source before stating facts: file contents
→ read the file; CLI behavior → `--help` of the exact subcommand; git
state → `git`; library versions and APIs → the installed package or
first-party docs. Verify before implementing, not after an error.
Earlier scans of the repository are not current: re-read a file at the
moment a claim depends on it.

## Security-Sensitive Code

Agent-written code is a draft a named developer owns. Any change
touching authentication, authorization, cryptography, input handling,
money, payments, file uploads, or dependencies is flagged as such in
the commit body and in `handoff.md`, and is `high` tier. Secrets never
enter code, config, docs, commits or chat — reference them by name from
`.env` (gitignored) or CI variables. If a secret appears in output, say
so and advise rotating it; do not repeat it.

## Language Policy

English for all code, comments, documentation, commit messages and
repository artifacts. Russian for conversation with the user.

## Documentation Layout

Three coexisting systems store different objects. Put content where
its object belongs; do not duplicate across systems — prefer one
authority plus references.

| Object | Location |
|---|---|
| What the system must do (living requirements per capability) | `openspec/specs/<capability>/spec.md` |
| Work in flight (proposal, design, tasks, review, handoff) | `openspec/changes/<id>/` — archived after merge |
| Why a decision was made (append-only log) | `docs/adr/ADR-NNN-*.md` — superseding means a new ADR, never editing the old one |
| How to use / understand (Diátaxis) | `docs/tutorials/`, `docs/how-to/`, `docs/reference/` describe only what WORKS; `docs/explanation/` may describe decided design citing its ADR |
| Cross-change roadmap | `openspec/ROADMAP.md` — updated within changes |
| Agent process rules (auto-loaded) | `AGENTS.md` (+ `.claude/rules/`) |
| Stack facts agents need every session | the Stack section below |

## Changing This Process

The process grows only against evidence. A new rule, check or ADR is
adopted only when the same defect appeared in several distinct changes
(not one incident) AND the proposal names what manual step it retires.
Prefer, in order: making the defect impossible by construction; an
existing check; a new check; an executor procedure; a review
obligation. One-off incidents are fixed, not legislated.

### Claude Code-Specific Notes

- `.claude/rules/*.md` are auto-loaded (terse behavior; verify-don't-
  assume; language). `.claude/settings.json` holds the shared permission
  allow/deny list; personal overrides go to the gitignored
  `.claude/settings.local.json`.
- `.claude/commands/`: `/workflow:start`, `/workflow:status`,
  `/workflow:handoff`, `/workflow:fix-findings`, `/gate-review`,
  `/git:commit`, `/git:merge`. `/opsx:*` commands and the
  `openspec-*` skills are generated by `openspec init --tools
  claude,codex`; refresh them with `openspec update`, never edit by hand.
- IDE MCP endpoint (`.mcp.json`) is machine-local and gitignored — see
  `docs/how-to/local-mcp.md`.

### Codex-Specific Notes

- Reads this file natively. Invoked for gate reviews either headless by
  `scripts/gate-run.sh` (`auto`) or interactively by the user with the
  prompt the runner printed (`manual`); writes only `review.md`, runs
  no git write commands.
- Uses the `.agents/skills/openspec-*` skills generated by `openspec init`.
- Repo-local `.codex/config.toml` is untracked and machine-specific.

<!-- STACK:BEGIN -->
## Stack

Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 + Alembic ·
PostgreSQL 16 + pgvector · CLIP / DINOv2 · uv · pytest · ruff · mypy.
Full requirements: `docs/explanation/requirements.md` (the original
brief); ordered plan: `openspec/ROADMAP.md`.

### Commands (all through `make`; Python runs via `uv run` on the host, the database in Docker)

| Command | Purpose |
|---|---|
| `make init` | first run: `uv sync`, start the database, `alembic upgrade head` |
| `make up` / `make down` | start / stop the database container |
| `make run` | `uvicorn --factory app.main:create_app --reload` |
| `make migrate` / `make revision MSG='…'` | apply migrations / autogenerate a revision |
| `make test` / `make lint` / `make fmt` / `make types` | pytest / ruff check / ruff format / mypy |
| `make lock-check` | `uv lock --check`: `uv.lock` matches `pyproject.toml` (CI syncs with `--frozen`, which does not check) |
| `make check` | **the gate floor**: `lock-check` + `lint` + format check + `types` + `test` — must be green before Gate 2 and merge |

### Layout

```
app/
  main.py            FastAPI app factory, routers, lifespan (lazy model registry)
  api/               routers by resource: assets.py, search.py, health.py
  core/              settings (pydantic-settings), logging, errors
  db/                engine/session, base, alembic env
  domain.py          frozen dataclasses, value domains, the model registry;
                     imports no framework, so every layer may depend on it
  storage.py         the media root: the only module that builds a path under it
  models/            SQLAlchemy ORM (Asset, Embedding, IndexingJob)
  repositories/      one per table; take a session, return domain objects,
                     never hand an ORM instance outwards
  schemas/           Pydantic request/response models — never the ORM classes
  services/          use cases: assets.py (upload, read, edit, delete), images.py
                     (inspection and thumbnails), indexing.py (the queue's policy
                     and its three steps — claim, execute, finish — plus the drain
                     both runners use), prune.py, readiness.py, tagging.py
  ml/                embedders behind one Protocol: base.py (protocol, normalisation,
                     the checkpoint guard), clip.py, fake.py (deterministic, no
                     weights), registry.py (lazy per-process cache), pool.py
                     (the threads loading and inference run on)
  cli.py             typer app: models warm and storage prune today; index-folder,
                     worker and demo-dataset later (the `worker` process of stage 3
                     calls the same functions in services/indexing.py)
ui/                  Streamlit demo: `app.py` declares the pages, `pages/` holds them,
                     `client.py` is the only thing that speaks HTTP and `shell.py` what
                     the pages share. Its own dependency group; imports nothing from
                     `app/`, which `tests/ui/test_layering_ui.py` proves
alembic/             migrations
tests/               unit/ (fake embedder, no DB), integration/ (pgvector, marked),
                     api/ (httpx against the app factory), models/ (real weights, on demand)
```

### Code style

- Type hints everywhere; `mypy --strict` on `app/`; ruff default rules +
  `I` (isort) + `B` + `UP`; line length 100.
- `async def` endpoints and repositories; model loading and inference are
  offloaded to the dedicated inference pool (`app/ml/pool.py`) or run in
  the worker process — never block the event loop.
- Pydantic schemas are separate from ORM models; validate at the edge.
- One `Embedder` Protocol (`key`, `dim`, `embed_text`, `embed_images`),
  returning unit-length float32 rows; models are loaded lazily through
  the registry, cached per process, and both loading and inference run
  on the inference pool, never on the event loop.
- Settings only via `pydantic-settings` from environment — no
  hard-coded paths, model names or thresholds.
- Repositories return domain objects; services compose them; routers
  translate to HTTP.

### Domain rules (from the brief)

- `assets(id, sha256, meta JSONB, tags[])` — the file path is derived
  from the id, never stored, never taken from a client;
  `embeddings(asset_id, model, vector, created_at)` — the `model` column
  is part of the identity: vectors of different models are never
  compared; `indexing_jobs` is the queue (at-least-once, idempotent
  upsert, leases). Full rules: `docs/explanation/requirements.md`.
- Vector dimension per model is fixed and checked on insert: one CHECK on
  `embeddings` carries both the model allowlist and each key's width, and
  the application declares the same registry in `app/domain.py`. One
  partial HNSW index per model over the dimension-cast expression, so
  every vector query must carry that cast (ADR-001).
- Similarity is cosine on L2-normalised vectors; the API exposes
  `min_score`, `limit`/`offset` with `has_more` (no total); results
  carry `score`. Errors are RFC 9457 problem details.
- Index choice (HNSW vs IVFFlat) is a per-model migration decision,
  recorded in an ADR.
- Uploaded files are stored outside the web root under a generated name;
  the original filename is metadata only. Every path under `MEDIA_ROOT` is
  built in `app/storage.py` from an identifier the service generated — nothing
  a client sends reaches a path — and the whole request body is bounded by
  `app/core/body_limit.py`, because the framework parses a multipart request
  before an endpoint runs.

### Risk-tier triggers specific to this project

`high`: file upload and path handling, deletion of assets/embeddings,
model downloads and any network egress from the service, authentication
if added, Alembic migrations that drop or rewrite data. `medium`:
endpoints, search logic, indexing. `low`: docs, settings wiring, UI
polish.

### Testing

- Unit tests use `ml/fake.py` (deterministic vectors) — real models are
  never loaded in unit tests or CI.
- Integration tests (`-m integration`) need the pgvector container and
  cover: dimension check on insert, cosine ordering, threshold and
  pagination, model isolation.
- API tests via `httpx.AsyncClient` against the app factory with the fake
  embedder injected.
<!-- STACK:END -->
