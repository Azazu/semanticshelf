# Proposal — write-requirements-spec

**Risk-Tier:** low

## Why

`docs/explanation/requirements.md` is a Russian copy of the portfolio brief: it names features but fixes no behavior (upload limits, model identity, score semantics, pagination, job semantics, API shape), so every implementing change would have to re-interview the user before it could write a spec. A full technical specification in English settles those decisions once and becomes the single source the per-capability specs in `openspec/specs/` are derived from.

## What Changes

- Rewrite `docs/explanation/requirements.md` from a brief into a full technical specification in English: goal and positioning, actors, functional requirements per capability, data model, API, technology stack with justification, non-functional requirements, stages with exit criteria, learning map, stretch goals and non-goals.
- Record every decision taken in the requirements interview of 2026-09-20 as a normative statement in the specification. The authoritative record is the "Decision record" section below; the specification must not contradict it, and any later change of a decision goes through a new change that edits both the specification and the roadmap.
- Reconcile `openspec/ROADMAP.md` against the specification: split the upload/indexing row into storage, background indexing and folder indexing, add the demo dataset, the indexing worker and the full-stack containerization, raise the tiers the AGENTS.md triggers require, keep change ids stable where scope did not move.
- Align the stack facts agents load every session (`openspec/config.yaml` context, the Layout block of `AGENTS.md`) with the specification, so no sibling artifact keeps an older rule (Celery as the worker option, a missing UI service).

## Decision record (interview of 2026-09-20)

Authoritative list of the interview outcomes. "Default" means the user accepted the executor's proposed default without amendment. Each row becomes at least one normative statement in `docs/explanation/requirements.md`; task 1.1 verifies row-by-row traceability.

| # | Question | Decision |
|---|---|---|
| D1 | Language | English for every repository artifact. Russian only in conversation and in a companion document for the user kept OUTSIDE the repository (`~/Projects/pet/SemanticShelf_TZ_RU.md`), refreshed after each change. The Russian brief inside the repository is superseded. |
| D2 | Reference project | The author's earlier work project is not a reference: SemanticShelf is written from scratch and nothing is ported from it. |
| D3 | Authorship marks | The repository is a public portfolio. No commit, file or PR text carries an agent trailer (`Co-Authored-By`) or any other agent authorship mark; the contributor graph shows the developer only. The process files that describe the AI-assisted workflow stay. |
| D4 | Review mode | `auto`: the executor runs Codex through `scripts/gate-run.sh`. Codex's quota is far lower than the executor's; on a quota or rate-limit failure the executor stops with a `blocked` handoff and notifies the user. |
| D5 | Stack | Default: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async on asyncpg, Alembic, uv, ruff, mypy strict, pytest, Docker multi-stage image, GitHub Actions. MIT licence. |
| D6 | Models | Default: CLIP ViT-L/14 (`openai/clip-vit-large-patch14`, 768-d joint space) for text→image and DINOv2-large (`facebook/dinov2-large`, 1024-d CLS embedding) for image→image, both through Hugging Face `transformers` on CPU. Model keys are stable identifiers in the database; Hugging Face names and cache path are settings. Loading is lazy through a registry; tests use a deterministic fake embedder. |
| D7 | Embedding storage | Default: one `embeddings` table keyed by `(asset_id, model)`; the dimension per model is fixed and checked both in the application and by the database; one HNSW cosine index per model; vectors of different models are never compared. The mechanism (partial expression indexes vs a table per model) is chosen in the schema change and recorded in ADR-001; HNSW vs IVFFlat is measured in a later change. |
| D8 | Background work | Default: no Redis, no Celery. Extraction runs outside the request from the first stage through `indexing_jobs` rows in PostgreSQL; stage 1 drains them with FastAPI `BackgroundTasks`, stage 3 replaces the runner by a separate worker process claiming jobs with `FOR UPDATE SKIP LOCKED`. The API contract (job status per asset and model) does not change between the two. |
| D9 | Upload handling | Default: multipart upload, allowed formats JPEG/PNG/WebP detected from content (not from the filename), size and pixel caps, SHA-256 content deduplication, files stored outside the web root under generated names, original filename kept as metadata only, re-encoded thumbnails for the UI. `high` tier. |
| D10 | Search surface | Default: `GET /api/v1/search/text` (CLIP), `POST /api/v1/search/image` (upload a picture, DINOv2), `GET /api/v1/assets/{id}/similar` (a stored asset, DINOv2); cosine similarity, optional `min_score`, `limit`/`offset` with `has_more` (no total), tag filters, `score` on every item. |
| D11 | Demo UI | Default: Streamlit as a separate Compose service that talks to the API over HTTP only. |
| D12 | Authentication and rate limiting | Default: non-goals. The service binds to loopback in development and is documented as "deploy behind a reverse proxy with authentication" for anything else. |
| D13 | Query language | User: English queries in the core stages (CLIP ViT-L/14 is English-only); multilingual queries are a stretch change that swaps the text encoder behind the `Embedder` protocol and measures the result. |
| D14 | Demo data | User: the author has no image set; a script downloads a bounded sample from a permissively licensed public dataset with tags derived from its metadata. Images never enter the repository; the source and its licence are documented. The dataset is chosen in the implementing change after a licence check. |
| D15 | Containerization | Default: development runs Python on the host with only PostgreSQL in Docker; a full Compose stack (api, worker, ui, db) with a multi-stage image arrives in stage 4 so `docker compose up` works on a clean machine. |
| D16 | CI and pushes | User: before a Gate 2 review the user pushes the branch and the CI run on the exact HEAD must be green. The executor never queries GitHub Actions itself: the user watches the run and reports a failure. The executor's duty is prevention: before asking for a push it runs locally every check CI runs (the `workflow` job's commands and `make check`). Recorded in `AGENTS.md`. |
| D17 | Deletion | Default: assets can be deleted (rows, embeddings, jobs and files); `high` tier per `AGENTS.md`. |

## Capabilities

### New Capabilities

None — this change writes documentation. Behavioral specs are created by the implementing changes, each deriving its delta from the specification written here. `.openspec.yaml` sets `skip_specs: true`.

### Modified Capabilities

None.

## Non-goals

- No application code, configuration, dependency, migration or `pyproject.toml` is added.
- No ADRs are written: the specification records requirements and the interview decisions; architectural decisions get their ADRs inside the implementing changes when the trade-off is actually faced (ADR-001 index layout, ADR-002 HNSW vs IVFFlat measurement, ADR-003 job queue in PostgreSQL).
- No per-capability spec in `openspec/specs/` is written here.
- The Russian portfolio source document (`Pet_Projects_Portfolio_Sopilko.md`, outside the repository) is not modified; the Russian companion document (D1) is written outside the repository and is not part of this change's diff.

## Impact

- `docs/explanation/requirements.md` — replaced whole (the Russian brief is superseded; a provenance line is kept).
- `openspec/ROADMAP.md` — rows split, added and re-tiered as listed above.
- `openspec/config.yaml` `context` and the Layout / Domain rules of `AGENTS.md` — brought in line with the specification (worker model, UI service, problem-details errors).
- New dependencies: none in this change. The specification *names* future dependencies (`transformers`, `torch` CPU wheels, `pillow`, `pgvector`, `asyncpg`, `structlog`, `streamlit`, `typer`) with a one-line justification each against the anti-overengineering rule; the implementing change still owns the final justification when it adds the package.
