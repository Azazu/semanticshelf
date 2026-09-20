# Roadmap

Ordered plan of upcoming OpenSpec changes — the single repository-
visible home of the cross-change plan. Updated WITHIN changes: at the
session-end protocol when the plan shifts, and at archive time when a
change completes (its row is removed; history lives in git).

Derived from section 7 of the technical specification
(`docs/explanation/requirements.md`); ids, order and tiers are the
same in both. Each row is a summary; the change's `proposal.md`
carries the full scope, exit criteria and the declared tier.

## Stage 0 — specification

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 0 | `write-requirements-spec` | the technical specification in English, the decision record of the requirements interview, roadmap and agent-context reconciliation | low |

## Stage 1 — skeleton, schema, CLIP, upload, background indexing

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 1 | `bootstrap-dev-environment` | uv project with the PyTorch CPU index, tool configs, `.env.example`, MIT `LICENSE`, Makefile targets working on an empty package, CI `python` job green | high |
| 2 | `scaffold-fastapi-app` | app factory, settings, structlog + request id, problem-details errors, `/health`, `/ready`, async engine, Alembic baseline, `/api/docs`, test layers with the fake-embedder fixture | medium |
| 3 | `add-assets-and-embeddings-schema` | `assets`, `embeddings`, `indexing_jobs` with dimension CHECK and per-model HNSW index, repositories, migration round trip in CI, ADR-001 | medium |
| 4 | `add-embedder-protocol-and-clip` | `Embedder` protocol, lazy registry, inference threadpool, fake embedder, CLIP adapter, `models warm`, on-demand real-model smoke | high |
| 5 | `add-asset-upload-and-storage` | asset CRUD, `/file`, `/thumbnail`, listing, tag/meta rules, storage layout, dedup, thumbnails, crash-safe writes, `storage prune` | high |
| 6 | `add-background-indexing` | transactional job enqueue, `BackgroundTasks` runner over the shared claim/execute/finish functions, `index_status`, `/jobs`, `/reindex`, leases, retries, ADR-003 | high |
| 7 | `add-folder-indexing-cli` | `typer` CLI, `index-folder` through the upload pipeline, summary, dry run | medium |

## Stage 2 — text→image search, demo data, demo UI

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 8 | `add-text-to-image-search` | `GET /search/text`, scores, `min_score`, `limit`/`offset`/`has_more`, `ef_search` bound, model isolation, `/tags`, `/stats` | medium |
| 9 | `add-demo-dataset` | `demo-dataset download/index`, licence check and notice, provenance meta, `make demo` | medium |
| 10 | `add-demo-ui` | Streamlit Search, Browse, Upload, Status pages; own dependency group; `make ui` | low |

## Stage 3 — image→image, filters, worker, index tuning

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 11 | `add-dinov2-image-search` | DINOv2 adapter, `POST /search/image`, `/similar`, `model` parameter, UI "Find similar" page | high |
| 12 | `add-tag-and-meta-filters` | `tags_all`, `tags_any`, `meta.<key>` inside the vector query on every search and listing; filtered-HNSW measurement | medium |
| 13 | `add-indexing-worker` | `worker` command with `SKIP LOCKED` claims, graceful shutdown, `INDEXING_RUNNER` switch, multi-worker test | high |
| 14 | `tune-vector-indexes` | HNSW vs IVFFlat per model, recall@10, p95, `ef_search` curve, `docs/how-to/benchmarks.md`, ADR-002 | low |

## Stage 4 — full stack, quality, docs

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 15 | `containerize-full-stack` | multi-stage Dockerfile, Compose `api`/`worker`/`ui`/`db` with healthchecks and volumes, CI image build, `make sca-image` | high |
| 16 | `harden-quality-and-docs` | README with screenshots, diagram and benchmarks, layering test, dependency audit in CI, ADR index, remaining how-to pages | low |

## Stretch

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 17 | `stretch-multilingual-queries` | multilingual text encoder behind the protocol, measured against English CLIP | medium |
| 18 | `stretch-style-search` | style embedding model as a third key with its own index | medium |
| 19 | `stretch-rag-captions` | generated captions/tags per image via a vision-language model; egress policy ADR | high |
