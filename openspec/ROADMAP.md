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

Done: every change of this stage is merged and archived. A picture can be
uploaded over HTTP or imported from a folder, is stored under a generated name,
and gets its vectors in the background. The history is in git and in
`openspec/changes/archive/`.

## Stage 2 — text→image search, demo data, demo UI

Done: every change of this stage is merged and archived. Words find pictures
(`GET /search/text`, with scores, a threshold and honest paging), `make demo`
fills a clean machine with a licence-filtered corpus from COCO val2017, and
`make ui` puts a Streamlit interface over the API — with the screenshots to
prove it in `docs/images/`. (Four pages when this stage closed; the fifth came
with the first change of stage 3.)

## Stage 3 — image→image, filters, worker, index tuning

Started: `add-dinov2-image-search` is merged and archived. A picture is a query
now — one sent in a request or one the store already holds — every search takes
the model that answers it, and `semanticshelf index missing` gives a model that
arrived late the vectors it has none of.

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 12 | `add-tag-and-meta-filters` | `tags_all`, `tags_any`, `meta.<key>` inside the vector query on every search and the listing; `hnsw.iterative_scan` for narrowed queries; `scan_limited` in the answer; `scripts/filter_benchmark.py` + `docs/how-to/benchmarks.md` | high |
| 13 | `add-indexing-worker` | `worker` command with `SKIP LOCKED` claims, graceful shutdown, `INDEXING_RUNNER` switch, multi-worker test | high |
| 14 | `tune-vector-indexes` | HNSW vs IVFFlat per model, recall@10, p95, `ef_search` curve, extending `docs/how-to/benchmarks.md` (change 12 started it), ADR-002 | low |

## Stage 4 — full stack, quality, docs

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 15 | `containerize-full-stack` | multi-stage Dockerfile, Compose `api`/`worker`/`ui`/`db` with healthchecks and volumes, CI image build, `make sca-image` | high |
| 16 | `harden-quality-and-docs` | README with screenshots, diagram and benchmarks, layering test, dependency audit in CI, ADR index, remaining how-to pages, OpenAPI examples backfilled on the operations of changes 2-7 (FR-OPS-4) | low |

## Stretch

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 17 | `stretch-multilingual-queries` | multilingual text encoder behind the protocol, measured against English CLIP | medium |
| 18 | `stretch-style-search` | style embedding model as a third key with its own index | medium |
| 19 | `stretch-rag-captions` | generated captions/tags per image via a vision-language model; egress policy ADR | high |
