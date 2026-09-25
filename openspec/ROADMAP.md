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

Started: `add-dinov2-image-search`, `add-tag-and-meta-filters` and
`add-indexing-worker` are merged and archived. A picture is a query now — one sent in a request or one the store
already holds — every search takes the model that answers it, and `semanticshelf
index missing` gives a model that arrived late the vectors it has none of. Every
search and the listing narrow by tags and metadata inside the vector query, an
answer says when the scan stopped at its own bound rather than at the end of the
ranking, and `scripts/filter_benchmark.py` measures which plan answers at which
selectivity (`docs/how-to/benchmarks.md`) — the numbers change 14 starts from.
And the queue finally has the process it was built for: `semanticshelf worker`
claims with `SKIP LOCKED` alongside any number of its own kind, stops after the
batch it holds when a signal arrives, and `INDEXING_RUNNER` decides whether the
API and the import commands do the work themselves or leave all of it to it.
Change 14 closes the stage: `scripts/index_benchmark.py` measures what the
vector index gives up — recall@10 against an exact ranking, the `ef_search`
curve, p95, build time and size, HNSW against IVFFlat, per model — and
**ADR-002** records what that decided. It decided to change nothing: at the size
the requirements name, the shipped index returns the whole ranking at the effort
the service sets, and IVFFlat has no strict iterative order for a narrowed
search to rest on.

| # | Change id | Scope (summary) | Tier |
|---|---|---|---|
| 12 | `add-tag-and-meta-filters` | `tags_all`, `tags_any`, `meta.<key>` inside the vector query on every search and the listing; `hnsw.iterative_scan` for narrowed queries; `scan_limited` in the answer; `scripts/filter_benchmark.py` + `docs/how-to/benchmarks.md` | high |
| 13 | `add-indexing-worker` | `semanticshelf worker` with `SKIP LOCKED` claims and a bounded poll; a stop that finishes the batch it holds and a second signal that does not; `INDEXING_RUNNER` governing the API and both importing commands; two child processes on one queue as the evidence | high |
| 14 | `tune-vector-indexes` | HNSW vs IVFFlat per model, recall@10 against an exact ranking, p95, `ef_search` curve, extending `docs/how-to/benchmarks.md` (change 12 started it), ADR-002; the schema guard shared by both benchmarks | high |

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
