# SemanticShelf — Technical Specification

**Status:** normative for all OpenSpec changes listed in `openspec/ROADMAP.md`.
**Provenance:** expanded from the SemanticShelf brief of the author's portfolio plan (project 3). Behavioral decisions were fixed in the requirements interview of 2026-09-20; their authoritative record (D1–D17) lives in the proposal of the change `write-requirements-spec` and is traced to sections of this document in Appendix A. A decision changes only through a new change that edits this document and the roadmap together.

Per-capability requirements with SHALL statements and scenarios are derived from this document into `openspec/specs/<capability>/spec.md` by the implementing changes; where the two disagree, the spec is corrected to match this document or this document is amended in the same change — never left inconsistent.

---

## 0. Goal and positioning

SemanticShelf is a semantic search service over images: pictures are uploaded or indexed from a folder, embeddings are extracted by open-source vision models and stored in PostgreSQL with pgvector, and clients search by text ("a red dragon in the fog") or by example image. It is built as a portfolio project on a domain the author knows from production research on embedding-based search over an image asset library.

What it demonstrates:

- **Python 3.12 / FastAPI** as an async service with Pydantic v2 validation at the edge, typed SQLAlchemy 2 ORM, Alembic migrations and a clean repository → service → router layering.
- **ML models in a backend service**: CLIP ViT-L/14 for the joint text–image space and DINOv2-large for visual similarity, behind one `Embedder` protocol, loaded lazily, never blocking the event loop, replaced by a deterministic fake in tests.
- **PostgreSQL 16 + pgvector** as the only database: relational data, JSONB metadata, text arrays for tags, per-model HNSW cosine indexes, and a job queue in the same database (`FOR UPDATE SKIP LOCKED`) — no Redis, no Celery, no second store.
- **Search design**: cosine scores exposed to the client, a similarity threshold, bounded pagination that is honest about approximate nearest-neighbour results (`has_more`, no total), filters combined with vector search, model isolation in the schema.
- **Resource-aware engineering**: heavy extraction outside the request, a separate worker process, measured index and CPU trade-offs recorded in ADRs.
- **Secure input handling**: uploads validated by content, stored under generated names outside the web root, size and pixel caps, deduplication by content hash.
- **A demo UI** (Streamlit) so the project is usable and screenshot-able, not API-only.
- **Engineering discipline**: `mypy --strict`, ruff, a unit / integration / API test pyramid, GitHub Actions with a pgvector service, multi-stage Docker image and a one-command Compose stack, ADRs, and an AI-assisted development workflow with independent review gates (`AGENTS.md`, `docs/adr/ADR-000-agent-workflow.md`).

Interview talking points the design must keep true: the `model` column is part of an embedding's identity and vectors of different models are never compared; embedding extraction never runs inside a request handler; the ANN index is measured, not assumed (recall and latency in an ADR); the upload path never trusts the filename or the declared content type; CLIP's English-only text encoder is a stated limit and the protocol makes the encoder swappable.

---

## 1. Actors and trust boundary

There is no authentication in the core stages (D12). The service is a single-tenant tool; every caller has the same rights.

| Actor | How it uses the service |
|---|---|
| **API client** | any HTTP client: uploads assets, searches, reads files and thumbnails, deletes assets |
| **Demo UI** | the Streamlit service; an API client with no privileges of its own, talks HTTP only |
| **Operator** | runs the CLI on the host or in the container: folder indexing, demo dataset, worker, maintenance |

Trust boundary: the API binds to loopback in development and is published on a Docker network only in the full stack. The README states that exposing the service beyond a trusted network requires a reverse proxy with authentication in front of it; authentication inside the service is a non-goal (§10).

---

## 2. Functional requirements

Requirement ids (`FR-<AREA>-<n>`) are stable references for specs, tasks and tests. Wording: SHALL = mandatory, SHOULD = expected unless a documented reason exists, MAY = optional.

### 2.1 Assets and upload (AST)

- **FR-AST-1** A client SHALL create an asset by `POST /api/v1/assets` (multipart): one `file` part (required), optional `tags` (repeated field or comma-separated), optional `meta` (a JSON object as a string, ≤ 8 KB). The response is 201 with the asset representation (FR-AST-8) and a `Location` header.
- **FR-AST-2** The file SHALL be accepted only if its content decodes as JPEG, PNG or WebP. The format is detected from the bytes (Pillow), never from the filename extension or the `Content-Type` part header; a mismatch between the declared type and the detected one is not an error, the detected format wins. Anything else → 415 problem details naming the detected type when Pillow recognises it.
- **FR-AST-3** Limits, all settings with defaults: `MAX_UPLOAD_BYTES` = 20 MiB (request body checked before decoding; over the limit → 413), `MAX_IMAGE_PIXELS` = 40 000 000 (decoded width × height; over → 422 `image-too-large`), minimum side 32 px (under → 422). Decoding uses `Image.verify()` followed by a fresh open, with the pixel cap applied before any pixel is allocated, so a decompression bomb is refused, not decoded.
- **FR-AST-4** Deduplication by content: the SHA-256 of the uploaded bytes is unique among assets. A second upload of identical bytes → 409 problem details with `existing_asset_id`; nothing is written. Different bytes of the "same" picture (re-encoded, resized) are different assets — perceptual deduplication is a non-goal.
- **FR-AST-5** Storage: the original bytes are written unchanged to `MEDIA_ROOT/<shard>/<asset-id>.<ext>` where `<asset-id>` is the server-generated UUID, `<ext>` follows the detected format (`jpg`, `png`, `webp`) and `<shard>` is the first two hex characters of the id. `MEDIA_ROOT` is outside any static-file directory; nothing under it is served by path. The original filename is kept in `original_filename` as metadata only, trimmed to 255 characters, with control characters and path separators removed.
- **FR-AST-6** A thumbnail SHALL be produced at upload: longest side **at most** 256 px, WebP quality 80, re-encoded from the decoded pixels (so EXIF, ICC and any embedded payload of the original are not carried), stored beside the original as `<asset-id>.thumb.webp`. A picture whose longest side is already under 256 px keeps its own size: enlarging it would spend bytes to invent detail that is not there, and the minimum accepted side is 32 px, so such pictures are normal rather than exceptional. Failure to produce a thumbnail fails the upload (the write is one unit: no asset row without its two files).
- **FR-AST-7** Write order and crash safety: files are written to a temporary name in the target directory and renamed into place; the database row is inserted after both files exist; if the insert fails the files are removed. An asset row therefore never points at a missing file, while a crash between the rename and the insert can leave orphan files — `python -m app.cli storage prune` (FR-CLI-4) lists and removes them.
- **FR-AST-8** Asset representation (JSON): `id`, `created_at`, `content_type`, `width`, `height`, `size_bytes`, `sha256`, `original_filename`, `source` ∈ {`upload`, `folder`}, `tags`, `meta`, `index_status` (a map model key → `pending` | `running` | `done` | `failed`, see FR-IDX-4), `links.file`, `links.thumbnail`, `links.similar`.
- **FR-AST-9** Reads: `GET /api/v1/assets/{id}` (200 / 404), `GET /api/v1/assets/{id}/file` (the original bytes with the detected content type, `Content-Disposition: inline; filename="<id>.<ext>"`, `Cache-Control: private, max-age=86400`, ETag = sha256), `GET /api/v1/assets/{id}/thumbnail` (same headers, `image/webp`). File responses are streamed from disk; no image is loaded into memory to serve it.
- **FR-AST-10** Listing: `GET /api/v1/assets` with `limit` (default 20, max 100), `offset` (max 10 000), `tags_all`, `tags_any` (FR-FLT-2), `source`, `index_status=<model>:<status>`; ordered by `created_at` desc, `id` desc; the response carries `items`, `limit`, `offset`, `has_more` (computed by fetching `limit + 1`). No `total` (§4, stability rules).
- **FR-AST-11** Update: `PATCH /api/v1/assets/{id}` accepts `tags` and/or `meta` as JSON merge-patch semantics on the asset (`meta: null` clears it, an omitted field is untouched); the file is immutable.
- **FR-AST-12** Deletion: `DELETE /api/v1/assets/{id}` removes the row, its embeddings and jobs (`ON DELETE CASCADE`) in one transaction, then removes both files after the commit (a failure to unlink is logged at `warning` and left to `storage prune`). Repeating the call → 404 (deletion is not idempotent at the HTTP level: the second caller is told the asset does not exist). A job running for the asset finishes into nothing: the embedding upsert fails on the foreign key and the worker acknowledges the job as `failed` with reason `asset-deleted`, no retry (FR-IDX-6). Deletion is `high` tier in the workflow sense (D17).

### 2.2 Tags and metadata (TAG)

- **FR-TAG-1** A tag SHALL match `^[a-z0-9][a-z0-9_-]{0,63}$` after normalisation (trimmed, lower-cased, Unicode NFKC). Up to 32 distinct tags per asset; duplicates collapse; an invalid tag → 422 naming the value.
- **FR-TAG-2** `meta` is a free-form JSON object (top level must be an object, ≤ 8 KB serialised, nesting depth ≤ 4). The service never interprets it except for the filters of FR-FLT-3 and the demo-dataset provenance keys (`dataset`, `dataset_id`, `licence`, `author`, `source_url`) that FR-CLI-3 writes.
- **FR-TAG-3** `GET /api/v1/tags` returns tags with their asset counts, ordered by count desc then name, `limit` ≤ 500 — the UI's tag cloud and filter source.

### 2.3 Embedders and models (MDL)

- **FR-MDL-1** One `Embedder` protocol: `key: str` (stable model key), `dim: int` (known without loading anything), `embed_text(texts: Sequence[str]) -> EmbeddingResult`, `embed_images(images: Sequence[PIL.Image]) -> EmbeddingResult`. The result carries `vectors: ndarray[n, dim]` and one truncation flag per vector, so a caller can tell that the answer describes less than it asked about; a model with no text tower raises `TextNotSupportedError` rather than returning a sentinel a caller could store. Vectors are L2-normalised `float32`, and a row of length zero is refused rather than divided into `nan`; cosine similarity is therefore the dot product and pgvector's `<=>` (cosine distance) and `<#>` (negative inner product) rank identically.
- **FR-MDL-2** Models in the core stages, with their stable keys (the value of `embeddings.model`) and dimensions:

  | Key | Hugging Face model (setting) | Dim | Used for |
  |---|---|---|---|
  | `clip-vit-l14` | `openai/clip-vit-large-patch14` (`CLIP_MODEL_NAME`) | 768 (projection space) | text→image (text and image towers) |
  | `dinov2-large` | `facebook/dinov2-large` (`DINOV2_MODEL_NAME`) | 1024 (CLS token after the final layer norm) | image→image |

  The key is a repository constant; the Hugging Face name is a setting so a compatible checkpoint (a fine-tune, a mirror) can be substituted without a schema change. Changing to a model with a different dimension or embedding space is a new key, a migration and a re-index (§3.2, §9).
- **FR-MDL-3** Loading is lazy through a per-process registry: no model is loaded at import time or at application start unless `MODEL_WARMUP` lists keys to load in the lifespan. The first request that needs a model pays the load once; the registry is thread-safe (one load per key under a lock). Weights are downloaded by `transformers` into `MODEL_CACHE`, passed explicitly as the loader's cache directory, on first use and never at build time; `HF_HUB_OFFLINE=1` is honoured for air-gapped runs with a pre-filled cache.
- **FR-MDL-4** Inference runs on the CPU (`torch` CPU wheels). There is no device setting: CPU-only is a project constraint (§10), and a build that cannot be configured onto a GPU cannot half-run on one. Thread count follows `TORCH_NUM_THREADS` (default `0`: torch's own choice, one thread per physical core), which a container with a CPU quota SHOULD set to that quota. All inference runs in `torch.inference_mode()` and in batches (`EMBED_BATCH_SIZE`, default 8).
- **FR-MDL-5** Neither inference nor loading ever runs on the event loop: both go through a dedicated, bounded pool of worker threads owned by the application (`INFERENCE_WORKERS`, default 2), so a burst of searches cannot starve the threadpool that serves file reads. Loading is the larger half — it reads gigabytes from disk or the network — so the asynchronous path obtains an embedder through that pool as well, and warm-up at start uses the same path. Batch extraction runs in the worker process (§2.4).
- **FR-MDL-6** `app/ml/fake.py` implements the protocol deterministically (a hash of the input to a fixed-dim unit vector, with text and an image carrying the same label in its `info` dictionary landing near each other; it never looks at pixels, so no result of it is evidence about a real model) so unit, API and integration tests exercise ordering, thresholds and model isolation without weights. Real models are never loaded in `make check` or CI; a `models`-marked smoke test (`make test-models`) loads each real model once, asserts `dim` and normalisation, and runs on demand only.
- **FR-MDL-7** Consistency is checked by two different mechanisms, because they can see different things.
  - **(a) Application against schema.** The readiness probe (FR-OPS-2) reads the dimension constraint from the database catalog and compares it with the dimension the application declares for every enabled key (§3.2), reporting `not ready` on a mismatch. It loads no model, and it catches a schema and a build that disagree — a migration not run, a key enabled too early.
  - **(b) Key against checkpoint.** No query can see inside a set of weights, so the adapter itself compares the width the loaded checkpoint actually produces with the width its key declares, and refuses to return an embedder on a mismatch. This runs at load, before any vector exists, and it is the only mechanism that catches a key pointed at the wrong weights.

### 2.4 Indexing jobs (IDX)

- **FR-IDX-1** Creating an asset (upload or folder indexing) SHALL enqueue one `indexing_jobs` row per enabled model key (`ENABLED_MODELS`, default: every key the build implements — a default configuration must be able to start) in the same transaction as the asset row. The request never extracts an embedding.
- **FR-IDX-2** Stage 1 runner: after the transaction commits, a FastAPI `BackgroundTasks` callback drains pending jobs (bounded batch) in the API process through the same claim/execute/finish functions the worker later uses. Stage 3 worker: `python -m app.cli worker` runs a loop that claims jobs with `SELECT … FOR UPDATE SKIP LOCKED` (batch `WORKER_BATCH_SIZE`, default 4), extracts, upserts and finishes; several worker processes MAY run concurrently without coordination. When the worker is configured (`INDEXING_RUNNER=worker`) the API enqueues only. The HTTP contract is identical under both runners.
- **FR-IDX-3** Job lifecycle: `pending` → `running` (claimed; `started_at`, `attempts + 1`, `lease_expires_at = now + JOB_LEASE_SECONDS`, default 600) → `done` (`finished_at`) or `failed` (`last_error`, ≤ 2 KB, exception class and message, never a stack trace, never file contents). A `running` job whose lease expired is reclaimable (the runner crashed): claiming treats `running AND lease_expires_at < now()` like `pending`. Delivery is at-least-once; the embedding write is an upsert on `(asset_id, model)`, so a repeated execution is harmless.
- **FR-IDX-4** `index_status` in the asset representation is derived from the latest job per model: `pending`, `running`, `done`, `failed`. `GET /api/v1/assets/{id}/jobs` lists the jobs with `attempts`, timestamps and `last_error`.
- **FR-IDX-5** Retries: a failing job returns to `pending` with exponential backoff (`available_at = now + 2^attempts × 10 s`) up to `JOB_MAX_ATTEMPTS` (default 3), then `failed`. `POST /api/v1/assets/{id}/reindex` (optional `models` list) resets the selected jobs to `pending` with `attempts = 0` — the only way a `failed` job runs again.
- **FR-IDX-6** A job whose asset no longer exists ends with the asset: `ON DELETE CASCADE` removes the job row together with everything else derived from the asset (FR-AST-12), so there is no row left to carry a failure. A runner that was executing such a job discovers it when its finishing update matches nothing; it SHALL discard its result, SHALL NOT recreate the job, and SHALL NOT retry. The earlier wording of this requirement — finished as `failed` with `last_error = asset-deleted` — described a state the schema cannot hold, and was corrected in change 6 (Gate 1, finding 1).
- **FR-IDX-7** Extraction reads the stored original through the same decoder as the upload (FR-AST-3 caps apply again — a file replaced on disk cannot bypass them) and converts to RGB before the model's processor.
- **FR-IDX-8** Concurrency and crash behaviour are tested against real PostgreSQL: two claimers never take the same job; a lease that expired is reclaimed exactly once; an upsert after a duplicate delivery leaves one row.

### 2.5 Text→image search (TXT)

- **FR-TXT-1** `GET /api/v1/search/text?q=<text>&limit&offset&min_score&tags_all&tags_any` embeds `q` with the CLIP text tower and returns the nearest assets by cosine similarity of the `clip-vit-l14` image embeddings.
- **FR-TXT-2** `q` is required, 1–256 characters after trimming; CLIP truncates at its context length (77 tokens) and the response states `query_truncated: true` when that happened.
- **FR-TXT-3** Result item: `{asset: <FR-AST-8>, score: float}` with `score = 1 − cosine_distance` ∈ [−1, 1]; items are ordered by score desc, `asset.id` asc for ties. Only assets whose `clip-vit-l14` job is `done` can appear.
- **FR-TXT-4** The response is `{items, limit, offset, has_more, model: "clip-vit-l14", query_truncated}`; `has_more` is computed by fetching `limit + 1` candidates. No total (§4).
- **FR-TXT-5** The query is English: CLIP ViT-L/14 was trained on English captions and other languages degrade to near-random ranking. The API does not translate; the README says so; a multilingual encoder is a stretch change (§9, D13).

### 2.6 Image→image search (IMG)

- **FR-IMG-1** `POST /api/v1/search/image` (multipart `file` plus the query fields of FR-TXT-1 as form fields) decodes the picture under the upload rules (FR-AST-2/3, without storing anything), embeds it with `dinov2-large` in the inference threadpool and returns the nearest assets by cosine similarity of the `dinov2-large` embeddings. The query image is never persisted.
- **FR-IMG-2** `GET /api/v1/assets/{id}/similar?limit&offset&min_score&tags_all&tags_any` uses the stored `dinov2-large` embedding of the asset as the query (no inference), excludes the asset itself, and → 409 `not-indexed` when its DINOv2 job is not `done`.
- **FR-IMG-3** Item and envelope shapes are those of FR-TXT-3/4 with `model: "dinov2-large"`.
- **FR-IMG-4** Both search endpoints MAY take `model=<key>` to select another embedder that supports the query modality (a CLIP image→image search, a future style model); an unsupported combination → 422. Cross-model comparison is impossible by construction: the query is embedded by the model whose stored vectors are searched.

### 2.7 Filters, threshold and pagination (FLT)

- **FR-FLT-1** `min_score` (float in [−1, 1], optional) drops items below the threshold after ranking. The default is no threshold; the README documents typical ranges per model (CLIP text–image scores cluster around 0.2–0.35; DINOv2 near-duplicates exceed 0.9) so clients can choose.
- **FR-FLT-2** `tags_all` (every listed tag present, `@>`) and `tags_any` (at least one, `&&`) accept comma-separated tags normalised as in FR-TAG-1; both MAY be combined. Filters are applied in the SQL of the vector query (a `WHERE` on the joined `assets` row), not by post-filtering a fixed candidate list, so a narrow filter still returns `limit` items when they exist. The interaction with HNSW (pgvector's iterative scan / `ef_search` for filtered queries) is measured and recorded in the index ADR.
- **FR-FLT-3** `meta.<key>=<value>` MAY filter by top-level string equality in `meta` (`meta @> '{"key": "value"}'`); at most 5 such filters; keys match `^[a-z0-9_]{1,64}$`.
- **FR-FLT-4** Pagination is `limit` (default 20, max 100) and `offset`. On search endpoints `limit + offset` ≤ 1 000 (pgvector's `hnsw.ef_search` maximum, see FR-FLT-5); on listings `offset` ≤ 10 000. Pages are consistent only while the index does not change; the README states this. `total` is deliberately absent: with an approximate index and a threshold, an exact count costs a full scan.
- **FR-FLT-5** Every search query sets `hnsw.ef_search` for its transaction to `max(HNSW_EF_SEARCH, limit + offset)` (default 40, never above 1 000) so deep pages do not silently lose recall; a page with `limit + offset` > 1 000 → 422 `page-too-deep`.

### 2.8 CLI (CLI)

A `typer` application `python -m app.cli` (also `uv run semanticshelf`), sharing settings, repositories and services with the API.

- **FR-CLI-1** `index-folder <dir> [--recursive] [--tags a,b] [--meta '{"k":"v"}'] [--dry-run]` walks the folder, feeds every JPEG/PNG/WebP file through the upload pipeline (FR-AST-2…7 unchanged, `source = folder`, `original_filename` = the file's relative path), skips duplicates by SHA-256 with a counter, enqueues jobs, and prints a summary (`created`, `duplicates`, `rejected` with reasons). With `INDEXING_RUNNER=background` it then drains the jobs inline before exiting (progress bar); with `worker` it only enqueues.
- **FR-CLI-2** `worker [--once] [--batch N]` is the stage-3 runner of FR-IDX-2, with graceful shutdown on SIGTERM (finish the current batch, release nothing — leases expire).
- **FR-CLI-3** `demo-dataset download [--count 500] [--into .data/demo]` fetches a bounded sample of a permissively licensed public image dataset with a manifest, writes each image with a sidecar of tags derived from the dataset's own labels/keywords and provenance `meta` (FR-TAG-2), and prints the licence notice. The dataset is chosen and its licence recorded in the implementing change (`add-demo-dataset`); candidates are Unsplash Lite and COCO val2017. Images are never committed; `.data/` is gitignored. `demo-dataset index` runs `index-folder` on the result.
- **FR-CLI-4** `storage prune [--apply]` lists files under `MEDIA_ROOT` with no asset row and asset rows with missing files; `--apply` removes orphan files and marks assets with missing files `failed` for every model with `last_error = file-missing`. Without `--apply` it changes nothing.
- **FR-CLI-5** `models warm [key…]` loads the models once into `MODEL_CACHE` (for image builds and air-gapped hosts) and prints each key, dimension and load time.

### 2.9 Demo UI (UI)

Streamlit application in `ui/` (its own package, its own dependency group), a Compose service from stage 4; it knows only `API_BASE_URL`.

- **FR-UI-1** Pages: **Search** (text box → grid of thumbnails with scores, `min_score` slider, tag filter, "more" button using `offset`), **Find similar** (upload a picture → results; and from any thumbnail a "similar" action calling `/similar`), **Browse** (paginated grid with tag cloud from `/tags`, asset detail with metadata, index status, full-size image, delete with confirmation), **Upload** (file, tags, meta), **Status** (`/ready`, counts per index status, pending jobs).
- **FR-UI-2** The UI never touches the database or the filesystem; every image comes from `/file` and `/thumbnail` URLs. API errors (problem details) are shown as the `title` and `detail` fields, never as a traceback.
- **FR-UI-3** Screenshots of Search, Find similar and Browse on the demo dataset are part of the README (NFR-DOC-1).

### 2.10 Operations (OPS)

- **FR-OPS-1** `GET /health` → 200 `{"status":"ok","version":"<app version>"}` with no dependency check (liveness).
- **FR-OPS-2** `GET /ready` → 200 `{"status":"ready","checks":{...}}` when every check passes, otherwise 503 as problem details (§4) with `type` `/errors/not-ready` and a `checks` extension member holding one line per check. Checks: `SELECT 1` within `READINESS_TIMEOUT_SECONDS` (default 3 s), migration head applied (`alembic_version` equals the code's head; queried under the same budget and skipped when the database check failed — it runs concurrently with the model check, so the probe answers within about twice `READINESS_TIMEOUT_SECONDS` however many checks it grows), `MEDIA_ROOT` exists and is writable, and the schema's dimension constraint declares every enabled model with the width the application declares (FR-MDL-7a; the probe compares declarations and loads nothing, so it cannot and does not judge the weights themselves). A reason names exception classes, a timeout or a revision comparison, never an exception message (a driver message can carry the connection URL). Models are not loaded by the probe. Docker healthchecks use `/ready`.
- **FR-OPS-3** `GET /api/v1/stats` → asset count, counts per `(model, status)`, pending job age (oldest `created_at`), storage bytes — the UI's Status page and a smoke check for the README.
- **FR-OPS-4** OpenAPI 3.1 at `/api/openapi.json`, Swagger UI at `/api/docs`; every operation has a summary, a description and an example; problem-details responses are documented per status code.

---

## 3. Data model (PostgreSQL 16 + pgvector)

All timestamps `timestamptz` in UTC; primary keys UUID v4 generated by the database (`gen_random_uuid()`); every change is a reviewed, reversible Alembic migration (`downgrade()` tested by a down/up round trip on a throwaway database, NFR-REL-3). Names are physical; ORM classes live in `app/models/`.

### 3.1 `assets`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | server default `gen_random_uuid()` |
| `created_at` | timestamptz not null | default `now()` |
| `sha256` | char(64) not null, unique | content hash, deduplication (FR-AST-4) |
| `content_type` | text not null | `image/jpeg` \| `image/png` \| `image/webp`, CHECK |
| `file_ext` | text not null | `jpg` \| `png` \| `webp`, CHECK |
| `width`, `height` | integer not null | CHECK > 0 |
| `size_bytes` | bigint not null | CHECK > 0 |
| `original_filename` | text null | ≤ 255 chars, metadata only |
| `source` | text not null | `upload` \| `folder`, CHECK |
| `tags` | text[] not null | default `'{}'`, GIN index (`ix_assets_tags`) |
| `meta` | jsonb not null | default `'{}'`, GIN index with `jsonb_path_ops` (`ix_assets_meta`) |

Indexes: `ix_assets_created` on `(created_at desc, id desc)` for listings. The storage path is derived from `id` and `file_ext`; it is not stored.

### 3.2 `embeddings`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `asset_id` | uuid not null | FK `assets(id) ON DELETE CASCADE` |
| `model` | text not null | stable model key (FR-MDL-2), CHECK against the known keys |
| `vector` | vector | dimension per model, see below |
| `created_at` | timestamptz not null | |

Constraints and indexes:

- `UNIQUE (asset_id, model)` — the identity of an embedding includes the model; the upsert target of FR-IDX-3.
- Dimension check at the database: the migration that introduces a model key fixes its dimension in a CHECK (`model = 'clip-vit-l14' AND vector_dims(vector) = 768` …). The application checks the same before the write (a mismatch is a programming error → 500, logged, job `failed`). Adding a model is a migration that extends the CHECK and adds an index; nothing else changes.
- One HNSW cosine index per model. The mechanism — a partial expression index per key (`USING hnsw ((vector::vector(768)) vector_cosine_ops) WHERE model = 'clip-vit-l14'`) on the single table, or one physical table per model behind the same repository — is decided in `add-assets-and-embeddings-schema` and recorded in **ADR-001** with the query plans that prove the index is used. Build parameters (`m`, `ef_construction`) are settings of the migration and recorded there.
- The HNSW vs IVFFlat question (build time, recall@10 against an exact scan, p95 latency on the demo corpus, filtered-query behaviour) is measured in `tune-vector-indexes` and recorded in **ADR-002**, per model.

### 3.3 `indexing_jobs`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `asset_id` | uuid not null | FK `assets(id) ON DELETE CASCADE` |
| `model` | text not null | model key |
| `status` | text not null | `pending` \| `running` \| `done` \| `failed`, CHECK |
| `attempts` | integer not null | default 0 |
| `available_at` | timestamptz not null | default `now()`; backoff (FR-IDX-5) |
| `lease_expires_at` | timestamptz null | set while `running` |
| `last_error` | text null | ≤ 2 KB |
| `created_at`, `started_at`, `finished_at` | timestamptz | |

Indexes: `ix_jobs_claim` on `(status, available_at)` for the claim query; `ix_jobs_asset` on `(asset_id, model, created_at desc)` for `index_status`. Claim query shape (the mechanism of ADR-003): `SELECT … WHERE (status = 'pending' AND available_at <= now()) OR (status = 'running' AND lease_expires_at < now()) ORDER BY available_at LIMIT :n FOR UPDATE SKIP LOCKED`.

### 3.4 No persistence

Search queries, query images and thumbnails' derived data are not stored; there is no search log (non-goal). The CLI, the demo UI and the probes own no tables: they read and write the three tables above through the same repositories as the API. Model weights live in `MODEL_CACHE` on disk, outside the database.

---

## 4. API

- Base path `/api/v1`; JSON for bodies and responses (`application/json`), multipart for uploads, image bytes for `/file` and `/thumbnail`. OpenAPI and Swagger UI as in FR-OPS-4.
- Errors: RFC 9457 problem details (`application/problem+json`) for every non-2xx, including validation (422 with `errors[]` of `{loc, msg, type}` from Pydantic), 404, 405, 409, 413, 415, 500; `type` is a stable URI-reference slug (`about:blank` for plain HTTP errors, `/errors/<slug>` for the domain ones named in §2), `instance` carries the request id (NFR-OBS-1). No stack traces in any environment.
- Pagination envelope: `{items, limit, offset, has_more}`; search envelopes add `model` and, for text, `query_truncated`.

| Method & path | Purpose |
|---|---|
| `POST /api/v1/assets` | upload (FR-AST-1…7), 201 |
| `GET /api/v1/assets` | list with filters (FR-AST-10) |
| `GET /api/v1/assets/{id}` | representation (FR-AST-8) |
| `PATCH /api/v1/assets/{id}` | tags / meta (FR-AST-11) |
| `DELETE /api/v1/assets/{id}` | delete (FR-AST-12), 204 |
| `GET /api/v1/assets/{id}/file` · `/thumbnail` | bytes (FR-AST-9) |
| `GET /api/v1/assets/{id}/jobs` | indexing jobs (FR-IDX-4) |
| `POST /api/v1/assets/{id}/reindex` | reset jobs (FR-IDX-5), 202 |
| `GET /api/v1/assets/{id}/similar` | image→image by stored asset (FR-IMG-2) |
| `GET /api/v1/search/text` | text→image (FR-TXT-1) |
| `POST /api/v1/search/image` | image→image by uploaded picture (FR-IMG-1) |
| `GET /api/v1/tags` | tag counts (FR-TAG-3) |
| `GET /api/v1/stats` | counters (FR-OPS-3) |
| `GET /health` · `GET /ready` | probes (FR-OPS-1/2), outside `/api` |

Stability rules: field names are `snake_case`; ids are UUID strings; timestamps RFC 3339 UTC; scores are floats rounded to 4 decimals; the schema of any `/api/v1` response changes only additively — a breaking change means `/api/v2` (non-goal).

---

## 5. Technology stack and justification

Anti-overengineering rule (`openspec/config.yaml`): every component below names the role an existing one could not cover. The implementing change re-justifies a package when it actually adds it and pins versions in `uv.lock`.

| Component | Role | Why this, not something already present |
|---|---|---|
| Python 3.12, uv | runtime, environment and lock file | project premise; uv gives one reproducible lock for the host, CI and the image |
| FastAPI, Uvicorn, Pydantic v2, `pydantic-settings`, `python-multipart` | async HTTP, validation at the edge, settings from the environment, multipart uploads | project premise; multipart is required by Starlette for file uploads |
| SQLAlchemy 2 (async) + `asyncpg`, Alembic | typed ORM, async sessions, reviewed migrations | project premise; asyncpg is the standard async driver for SQLAlchemy with PostgreSQL |
| `pgvector` (Python) | `Vector` column type, asyncpg codec registration | the only client-side piece pgvector needs |
| `transformers` + `torch` (CPU wheels from the PyTorch index, pinned through `[tool.uv.sources]`) | CLIP and DINOv2 inference | one library covers both models; CPU wheels keep the image and lock small; no `open_clip`, no `sentence-transformers` |
| Pillow | decoding, verification, thumbnails | already a `transformers` image dependency; the decoder the caps of FR-AST-3 are written against |
| `structlog` | structured JSON logs with request-id binding across the threadpool and the worker | the standard library has no bound context; the JSON formatter and context plumbing would be ~100 lines of code with no portfolio value |
| `typer` | CLI (`index-folder`, `worker`, `demo-dataset`, `storage prune`, `models warm`) | one small dependency instead of hand-rolled argparse for five commands; same author and idioms as FastAPI |
| Streamlit | demo UI | the cheapest screenshot-able UI for a Python backend; a separate dependency group so the API image does not ship it |
| PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16`) | relational data, JSONB, arrays, vectors, the job queue | project premise; one store instead of Redis + Celery for a queue whose throughput is bounded by CPU inference anyway |
| pytest, `pytest-asyncio`, `httpx` (ASGI transport), `numpy` (fake embedder) | tests | project premise |
| ruff, mypy (strict), pre-commit (optional) | style and types | project premise |
| Docker multi-stage image on the uv base, Compose, GitHub Actions | delivery and CI | project premise |

Explicitly not used: Redis, Celery/arq/Dramatiq, RabbitMQ, Elasticsearch/OpenSearch, a dedicated vector database, an object store, a JavaScript frontend, any SaaS.

---

## 6. Non-functional requirements

### 6.1 Performance (local CPU, the demo corpus of ≥ 500 assets; measured, with the commands in `docs/how-to/benchmarks.md`)

- **NFR-PERF-1** Vector query: p95 ≤ 100 ms for `limit = 20` on 10 000 embeddings per model with the HNSW index (query embedding excluded); the index scan is shown by `EXPLAIN` in ADR-001, the latency is measured in ADR-002.
- **NFR-PERF-2** Query embedding on CPU: text ≤ 300 ms p95 after warm-up; a query image ≤ 3 s p95 (DINOv2-large at 224 px). The README states both so nobody expects GPU latencies.
- **NFR-PERF-3** Indexing throughput is documented (images per minute per worker on the reference machine), not targeted; the reference number and machine go into the benchmarks page.
- **NFR-PERF-4** Recall: HNSW recall@10 ≥ 0.95 against an exact scan on the demo corpus at the default `ef_search` (ADR-002); the trade-off curve (`ef_search` 20 → 200) is recorded.

### 6.2 Security

- **NFR-SEC-1** Secrets (database credentials) live in `.env` (gitignored) or CI variables and are referenced by name; `.env.example` holds placeholders. No secret is logged or echoed in an error.
- **NFR-SEC-2** Upload hardening (FR-AST-2…7): content sniffing, size and pixel caps before decoding, server-generated file names, no client-controlled path component anywhere, thumbnails re-encoded from pixels. Every guard has a failing-input test (`AGENTS.md`, `high` tier).
- **NFR-SEC-3** No path from a request reaches the filesystem: files are addressed by asset id; `MEDIA_ROOT` is never mounted as a static directory; symlinks inside `MEDIA_ROOT` are not followed when serving (`O_NOFOLLOW` semantics via a resolved-path check).
- **NFR-SEC-4** Network egress: the API and worker make no outbound request except the Hugging Face Hub download of model weights on first use (documented; `HF_HUB_OFFLINE=1` disables it) and the demo-dataset CLI (an operator action). Any future egress (captioning through an external model) is a `high`-tier change with its own ADR.
- **NFR-SEC-5** Untrusted input is bounded before processing: `q` ≤ 256 chars, tags ≤ 32 × 64 chars, `meta` ≤ 8 KB and depth ≤ 4, multipart body ≤ `MAX_UPLOAD_BYTES`. Nothing from a request is interpolated into SQL (parameters only) or shell.
- **NFR-SEC-6** Dependencies: `uv.lock` committed; the CI runs `pip-audit` (or `uv`'s equivalent when available) against the lock and fails on known HIGH/CRITICAL advisories with a fix; the Docker image is scanned before a release tag (`make sca-image`, stage 4).
- **NFR-SEC-7** No authentication (D12) is a stated boundary, not an oversight: the README's security notes explain the deployment shape (loopback / private network / reverse proxy with auth) and what the service does and does not protect.

### 6.3 Reliability

- **NFR-REL-1** An upload never depends on a model: the request stores and enqueues; extraction failures surface as job status, never as upload errors.
- **NFR-REL-2** Jobs are at-least-once with idempotent effects (FR-IDX-3); a crashed runner loses nothing beyond the lease timeout; the failure path (`failed`, `reindex`) is visible through the API.
- **NFR-REL-3** Every migration has a working `downgrade()`, proven by an integration test that CI runs: it creates a throwaway database, migrates to head, fingerprints the schema from the catalog, migrates down to base, up again, fingerprints once more and compares. It reads the catalog rather than shelling out to a dump tool, so it needs nothing the suite does not already have; it proves reversibility of the schema, not preservation of data, which no downgrade here claims.
- **NFR-REL-4** `/health` and `/ready` exist from the scaffold; Compose healthchecks gate the worker and the UI on the API being ready.
- **NFR-REL-5** A missing or corrupt file behind an asset (FR-CLI-4) degrades to a 404 on `/file` with a `warning`, never a 500.

### 6.4 Observability

- **NFR-OBS-1** JSON logs on stdout (structlog); every request has a request id (`X-Request-ID` honoured or generated, returned in the response and in `instance` of problem details); every log line of the search and upload paths carries it, and every worker line carries `job_id`, `asset_id` and `model`. Model load events log key, dimension and duration.
- **NFR-OBS-2** Slow-query visibility: the vector query logs its duration and `ef_search`; a request over `SLOW_REQUEST_MS` (default 1 000) is logged at `warning`.
- **NFR-OBS-3** Metrics endpoints (Prometheus) are a non-goal; `/api/v1/stats` covers what the UI and the README need.

### 6.5 Code quality and process

- **NFR-QA-1** Type hints everywhere; `mypy --strict` clean on `app/` and `ui/`; ruff with the rule set of `AGENTS.md`; `make check` is the gate floor and runs in CI on every push and pull request.
- **NFR-QA-2** Layering enforced by tests where cheap: routers contain no SQL and no model calls; repositories return domain objects, never Pydantic response models; `app/ml/` does not import `app/db/`. A dependency-rule test (import graph) fails on a planted violation.
- **NFR-QA-3** Every capability in section 2 has an `openspec/specs/<capability>/spec.md` by the time its change is archived; ADRs record the trade-offs listed in section 7 when they are faced.
- **NFR-QA-4** Process (D3, D4, D16): the AI-assisted workflow of `AGENTS.md` with risk tiers and independent Codex review gates in `auto` mode; no agent authorship marks in the repository; before a Gate 2 the user pushes the branch and reports the GitHub Actions result, while the executor reproduces every CI check locally beforehand so a red run is the exception.

### 6.6 Testing

Layers as in `AGENTS.md`: `tests/unit` (fake embedder, no database, no network), `tests/integration` (pgvector container, `-m integration`), `tests/api` (`httpx.AsyncClient` against the app factory with the fake embedder and a test database), `tests/models` (real weights, on demand only). Always-tested paths:

- upload: each accepted format; declared-type mismatch; every rejection class (unsupported format, over-size body, pixel cap, tiny image, decompression bomb fixture, invalid tag, invalid meta) with a failing input; deduplication → 409 with the existing id; file and thumbnail exist after 201; failed insert leaves no files;
- serving: content type and headers; a missing file → 404 with a warning; no path traversal by construction (test that ids are the only addressing);
- deletion: rows, embeddings, jobs and files gone; second delete 404; delete-then-job race → `failed asset-deleted`;
- jobs: enqueue in the same transaction; claim under concurrency (two sessions, `SKIP LOCKED`); lease expiry reclaim; backoff and max attempts; `reindex`; upsert idempotency;
- models: fake embedder determinism and normalisation; registry loads once under concurrent first use; `dim` mismatch → not ready; real-model smoke (on demand);
- search: cosine ordering on known vectors; `min_score`; `limit`/`offset`/`has_more`; tag and meta filters combined with the vector query; model isolation (a `dinov2-large` vector never appears in a `clip-vit-l14` search even with a compatible dimension fixture); `ef_search` bound; `query_truncated`; `/similar` excludes itself and refuses a non-indexed asset;
- migrations: down/up round trip; the dimension CHECK rejects a wrong-length vector; the unique `(asset_id, model)`;
- CLI: `index-folder` on a fixture tree (duplicates, rejects, dry run); `storage prune` lists and applies; `worker --once`;
- UI: a smoke test that the Streamlit script imports and renders its pages against a stubbed API (`streamlit.testing`).

### 6.7 Documentation and delivery

- **NFR-DOC-1** README: screenshots of the UI pages on the demo dataset, an architecture diagram (request path, job path, storage), `docker compose up` quick start, `make` targets, the security notes of NFR-SEC-7, the CPU latency expectations, the English-query limit, "what this shows" list, links to ADRs and to `docs/how-to/benchmarks.md`. Diátaxis layout under `docs/` per `AGENTS.md`.
- **NFR-DOC-2** `docker compose up` on a clean machine yields a working stack (db, api, worker, ui) whose first request triggers the model downloads; `make demo` (download the dataset sample, index it, wait for jobs) produces the corpus the screenshots were taken from.
- **NFR-DOC-3** GitHub Actions: strict OpenSpec validation and the script suites (`workflow` job), `make check` plus the integration suite against a pgvector service (`python` job) — the migration round trip of NFR-REL-3 is one of those tests, not a job of its own — and the dependency audit; from stage 4 a Docker image build. Status badge in the README. The executor never polls Actions; the user reports the run (D16).
- **NFR-DOC-4** `LICENSE` — MIT, added in the first change so every later file is covered.

---

## 7. Stages and changes

The stage plan is the source for `openspec/ROADMAP.md`; ids are stable across both. Each change's `proposal.md` refines scope and exit criteria; the tiers below are the minimum the triggers of `AGENTS.md` require. Compared with the brief, upload and indexing are split into storage, background indexing and folder indexing so each `high`-tier review stays small, and the queue moves out of the API process in its own change.

### Stage 1 — skeleton, schema, CLIP, upload, background indexing

| # | Change id | Scope | Tier | Exit criterion |
|---|---|---|---|---|
| 1 | `bootstrap-dev-environment` | `pyproject.toml` with uv, dependency groups and the PyTorch CPU index; ruff/mypy/pytest config; `.env.example`; `LICENSE` (MIT); Makefile targets of `AGENTS.md` working on an empty package; CI `python` job active with `make check` green on the empty app | high (CI infrastructure trigger) | `make init` and `make check` pass on a clean clone; CI green |
| 2 | `scaffold-fastapi-app` | app factory and lifespan, settings, structlog and request id, problem-details handlers, `/health`, `/ready` (DB check), async engine and session dependency, Alembic baseline (`CREATE EXTENSION vector`), `/api/docs`, test layers with the fake-embedder fixture | medium | `GET /health`, `/ready`, `/api/docs` work; a test per layer green |
| 3 | `add-assets-and-embeddings-schema` | `assets`, `embeddings`, `indexing_jobs` tables and migration, dimension CHECK, per-model HNSW index, repositories returning domain objects, migration round trip in CI, **ADR-001** | medium | integration tests: dimension check, unique `(asset_id, model)`, index used (`EXPLAIN`), round trip green |
| 4 | `add-embedder-protocol-and-clip` | `Embedder` protocol, lazy registry, dedicated inference threadpool, fake embedder, CLIP adapter (both towers), `models warm`, `tests/models` smoke, readiness dimension check | high (model download is network egress from the service) | fake-embedder tests green; `make test-models` loads CLIP and asserts 768 |
| 5 | `add-asset-upload-and-storage` | `POST/GET/PATCH/DELETE /assets`, `/file`, `/thumbnail`, listing, tags and meta rules, storage layout, dedup, thumbnails, crash-safe write order, `storage prune` | high | every rejection class has a failing-input test; dedup 409; delete cascades and unlinks |
| 6 | `add-background-indexing` | job enqueue in the upload transaction, `BackgroundTasks` runner over the shared claim/execute/finish functions, `index_status`, `/jobs`, `/reindex`, retries and leases, delete-race handling, **ADR-003** (queue in PostgreSQL) | high (concurrency) | concurrency and lease tests against PostgreSQL; an upload ends `done` for CLIP without a request-path model call (asserted) |
| 7 | `add-folder-indexing-cli` | `typer` app, `index-folder` through the upload pipeline, summary and dry run | medium | fixture-tree test: created / duplicates / rejected counts |

### Stage 2 — text→image search, demo data, demo UI

| # | Change id | Scope | Tier | Exit criterion |
|---|---|---|---|---|
| 8 | `add-text-to-image-search` | `GET /search/text`, score semantics, `min_score`, `limit`/`offset`/`has_more`, `ef_search` bound, `query_truncated`, model isolation, `/tags`, `/stats` | medium | ordering, threshold, pagination and isolation tests on fake vectors; `EXPLAIN` shows the HNSW scan |
| 9 | `add-demo-dataset` | `demo-dataset download/index`, licence check and notice, provenance meta, `make demo` | medium (egress from an operator command, not from the service) | 500 images indexed locally; licence recorded in `docs/reference/demo-dataset.md` |
| 10 | `add-demo-ui` | Streamlit Search, Browse, Upload, Status pages; dependency group; `make ui` | low | pages render against the API; screenshots produced |

### Stage 3 — image→image, filters, worker, index tuning

| # | Change id | Scope | Tier | Exit criterion |
|---|---|---|---|---|
| 11 | `add-dinov2-image-search` | DINOv2 adapter, `POST /search/image`, `/similar`, `model` parameter, UI "Find similar" page | high (model download) | isolation and self-exclusion tests; `make test-models` asserts 1024 |
| 12 | `add-tag-and-meta-filters` | `tags_all`, `tags_any`, `meta.<key>` on every search and listing, applied inside the vector query; filtered-HNSW measurement | medium | filter tests combined with ranking; narrow-filter recall recorded |
| 13 | `add-indexing-worker` | `worker` command with `SKIP LOCKED` claims, graceful shutdown, `INDEXING_RUNNER` switch, multi-worker test | high (concurrency) | two workers on one queue, no double claim; SIGTERM finishes the batch |
| 14 | `tune-vector-indexes` | HNSW vs IVFFlat per model: build time, recall@10, p95, filtered queries; `ef_search` curve; `docs/how-to/benchmarks.md`; **ADR-002** | low | numbers and commands published; the chosen parameters applied by migration if they changed |

### Stage 4 — full stack, quality, docs

| # | Change id | Scope | Tier | Exit criterion |
|---|---|---|---|---|
| 15 | `containerize-full-stack` | multi-stage Dockerfile on the uv base (runtime without dev/ui groups), Compose services `api`, `worker`, `ui`, `db` with healthchecks and volumes for media and the model cache, CI image build, `make sca-image` | high (CI infrastructure) | `docker compose up` on a clean checkout serves the UI and indexes an upload; CI builds the image |
| 16 | `harden-quality-and-docs` | README with screenshots, diagram and benchmarks, layering test (NFR-QA-2), dependency audit in CI, ADR index, remaining how-to pages | low | README complete; the layering test fails on a planted violation |

### Stretch (section 9)

| # | Change id | Scope | Tier |
|---|---|---|---|
| 17 | `stretch-multilingual-queries` | a multilingual text encoder in CLIP's space (or a multilingual CLIP variant as a new key) behind the protocol, measured against English CLIP on the demo corpus | medium |
| 18 | `stretch-style-search` | a style embedding model as a third key with its own index and `model=` support | medium |
| 19 | `stretch-rag-captions` | generated captions/tags per image through a vision-language model; egress policy ADR | high |

---

## 8. What each feature teaches (feature → mechanism)

| Feature | Mechanism exercised |
|---|---|
| Upload and storage | multipart streaming, content sniffing with Pillow, atomic file writes, generated names, JSONB and `text[]` columns, problem details |
| Embedders | a `typing.Protocol`, lazy singleton registry with locking, `transformers` CLIP/DINOv2, `torch.inference_mode`, normalisation, a dedicated threadpool, a deterministic fake for tests |
| Schema | pgvector `vector` columns, per-model dimension CHECK, HNSW cosine indexes (partial/expression or per-table), Alembic with a proven `downgrade()` |
| Jobs | transactional enqueue, `FOR UPDATE SKIP LOCKED`, leases and reclaim, at-least-once with idempotent upsert, backoff, a worker process with graceful shutdown |
| Search | `<=>` ranking, `ef_search` per transaction, threshold, `limit + 1` pagination, filters inside the ANN query, model isolation by construction |
| CLI | typer sharing the service layer, progress reporting, dry runs |
| UI | Streamlit over HTTP only, error surfaces, screenshots |
| Delivery | uv lock across host/CI/image, multi-stage Docker, Compose healthchecks, GitHub Actions with a pgvector service, migration round trip, dependency audit |
| Process | OpenSpec changes, risk tiers, independent review gates, ADRs, measured trade-offs |

---

## 9. Stretch goals

Taken only after stages 1–4 are archived, each as its own change:

- **Multilingual queries** (D13): swap or add the text encoder (a multilingual CLIP variant as a new model key, or a multilingual text tower aligned to CLIP's image space) and measure on the demo corpus; the English-only limit of FR-TXT-5 is lifted only with numbers.
- **Style search**: a style-embedding model as a third key (its own dimension, CHECK and index), exposed through `model=` on `/search/image` and `/similar`.
- **Generated captions and tags** through a vision-language model; if it runs outside the host it is egress and needs the ADR of NFR-SEC-4.
- **Re-embedding tooling**: a `models migrate <old-key> <new-key>` command that re-indexes the corpus under a new key and retires the old one, for model upgrades without downtime.
- **Perceptual deduplication** (near-duplicate detection through the DINOv2 index) as an operator report.

---

## 10. Non-goals

Fixed for the portfolio scope; each would be a separate specification change:

- Authentication, authorization, multi-tenancy, per-user collections, rate limiting (D12).
- Object storage (S3-compatible) or any storage backend other than the local filesystem; a storage interface exists only as far as the tests need it.
- GPU support as a tested configuration; video, audio, PDF or any non-image asset.
- Translation of queries; OCR; face recognition; content moderation.
- A search log, analytics, or a `total` count on search responses.
- Real-time updates (WebSocket/SSE); a JavaScript frontend; mobile apps.
- Prometheus metrics, tracing, any SaaS observability.
- Public hosting of a demo instance (CPU inference on a shared host is not a demo worth paying for); the Compose stack is the demo.
- Any naming of the author's employer, its internal systems or earlier work projects anywhere in the repository.

---

## Appendix A — decision traceability (interview of 2026-09-20)

| Decision | Where it is normative |
|---|---|
| D1 language, Russian companion outside the repository | this document; `AGENTS.md` Language Policy |
| D2 written from scratch, no reference project | §0, §10 (last bullet) |
| D3 no agent authorship marks | §6.5 NFR-QA-4; `AGENTS.md` Git Conventions |
| D4 auto review mode, quota stop | §6.5 NFR-QA-4; `AGENTS.md` Review Invocation |
| D5 stack and MIT licence | §5, §6.7 NFR-DOC-4, §7 change 1 |
| D6 CLIP ViT-L/14 and DINOv2-large, stable keys, lazy registry, fake embedder | §2.3 FR-MDL-1…7, §7 changes 4 and 11 |
| D7 one `embeddings` table, per-model dimension check and HNSW index, ADR-001/002 | §3.2, §7 changes 3 and 14 |
| D8 jobs in PostgreSQL, BackgroundTasks then a worker, no Redis/Celery | §2.4 FR-IDX-1…8, §3.3, §5, §7 changes 6 and 13 |
| D9 upload hardening | §2.1 FR-AST-2…7, §6.2 NFR-SEC-2/3 |
| D10 search surface, scores, threshold, pagination, filters | §2.5, §2.6, §2.7, §4 |
| D11 Streamlit over HTTP | §2.9, §5, §7 change 10 |
| D12 no auth, no rate limiting | §1, §6.2 NFR-SEC-7, §10 |
| D13 English queries, multilingual stretch | §2.5 FR-TXT-5, §9, §7 change 17 |
| D14 demo dataset by script, images outside the repository | §2.8 FR-CLI-3, §7 change 9 |
| D15 host + Docker db in development, full stack in stage 4 | §6.7 NFR-DOC-2, §7 change 15 |
| D16 push and green CI before Gate 2, executor prevents locally | §6.5 NFR-QA-4, §6.7 NFR-DOC-3; `AGENTS.md` Definition of Ready |
| D17 deletion of assets, high tier | §2.1 FR-AST-12, §7 change 5 |
