# Roadmap

Ordered plan of upcoming OpenSpec changes — the single repository-
visible home of the cross-change plan. Updated WITHIN changes: at the
session-end protocol when the plan shifts, and at archive time when a
change completes (its row is removed; history lives in git).

Derived from the SemanticShelf brief (`docs/explanation/requirements.md`),
stages 1–4. Each row is a summary; the change's `proposal.md` carries
the full scope, exit criteria and the declared tier.

## Stage 1 — skeleton and CLIP indexing

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 1 | `bootstrap-dev-environment` | pgvector compose service, uv project, Makefile targets, CI green on the empty app | low |
| 2 | `scaffold-fastapi-app` | app factory, settings, health route, SQLAlchemy async engine, Alembic baseline, `make check` wired | medium |
| 3 | `add-assets-and-embeddings-schema` | `assets` + `embeddings(model, vector)` with dimension check, HNSW index migration (ADR) | medium |
| 4 | `add-embedder-protocol-and-clip` | `Embedder` Protocol, lazy registry, fake embedder for tests, CLIP ViT-L/14 adapter | medium |
| 5 | `add-asset-upload-and-indexing` | upload endpoint, storage outside web root, background extraction, folder indexing command | high |

## Stage 2 — text→image search and demo UI

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 6 | `add-text-to-image-search` | `/search/text` with cosine similarity, threshold, pagination, scores | medium |
| 7 | `add-demo-ui` | minimal UI (Streamlit or static page) for query → results | low |

## Stage 3 — image→image, filters, indexes

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 8 | `add-dinov2-image-search` | DINOv2 adapter, `/search/image` (upload a picture → visually similar) | medium |
| 9 | `add-filters-and-tags` | tags/categories filters combined with vector search; pagination stability | medium |
| 10 | `tune-vector-indexes` | HNSW vs IVFFlat measurement per model, recorded in an ADR | low |

## Stage 4 — quality and stretch

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 11 | `harden-quality-and-docs` | mypy strict, integration suite in CI, README with examples and screenshots | low |
| 12 | `stretch-style-search` | CSD-ViT-L style embeddings as a third model | medium |
| 13 | `stretch-rag-captions` | generated captions/tags per image via a vision-language model; egress policy ADR | high |
