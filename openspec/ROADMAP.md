# Roadmap

Ordered plan of upcoming OpenSpec changes — the single repository-
visible home of the cross-change plan. Updated WITHIN changes: at the
session-end protocol when the plan shifts, and at archive time when a
change completes (its row is removed; history lives in git).

Derived from section 7 of the technical specification
(`docs/explanation/requirements.md`); ids, order and tiers are the
same in both. A row with a letter suffix (`4a`) is work a change
uncovered that section 7 could not foresee, inserted where it belongs
in the order. Each row is a summary; the change's `proposal.md`
carries the full scope, exit criteria and the declared tier.

## Stage 1 — skeleton, schema, CLIP, upload, background indexing

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
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
