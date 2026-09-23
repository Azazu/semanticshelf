# Handoff — add-dinov2-image-search

**Updated:** 2026-09-23 · claude
**State:** proposing
**Branch:** change/add-dinov2-image-search
**Security-sensitive:** likely — a picture arrives in a request body and is
decoded (FR-IMG-1), a second model is downloaded and loaded, and the API gains
a `model` parameter a client chooses. `AGENTS.md` puts file uploads, model
downloads and dependencies at `high`, and the roadmap already declares `high`.

## Done this session

Branch and scaffold only. The roadmap carried the row (change 11, tier high):
DINOv2 adapter, `POST /search/image`, `GET /assets/{id}/similar`, a `model`
parameter on both searches, and the "Find similar" page change 10 left out on
purpose.

Everything it needs is in place: the `Embedder` protocol with its lazy
per-process registry and the inference pool (change 4), one CHECK carrying the
model allowlist and each key's width plus one partial HNSW index per model
(change 3, ADR-001), the queue that indexes per model (change 6), the search
service with its bounds (change 8), and a demo corpus to try it on (change 9).

## Next step

`/opsx:propose add-dinov2-image-search`. What the proposal has to settle before
anything is written:

- **the schema decision.** `dinov2-large` is 1024-dimensional where CLIP is 768;
  the CHECK constraint and the HNSW index are per model, so this needs a
  migration — and migrations that touch constraints are exactly where change 4a
  came from;
- **what a second model does to indexing.** Every stored asset needs a DINOv2
  vector: is that a backfill command, or work queued for what exists, and what
  does `index_status` look like while half the corpus has one vector and not the
  other;
- **the query image is not stored** (FR-IMG-1), which means the upload pipeline
  is used for decoding and bounds but not for storage — a path that does not
  exist yet;
- **`/similar` excludes the asset itself** and answers 409 when its DINOv2 job
  is not `done` (FR-IMG-2), which is a new kind of refusal for this API;
- **the `model` parameter** (FR-IMG-4): which combinations are legal, and what a
  request for a model this build does not run answers — the 503 of change 8
  already has a shape to follow;
- **how much of change 8's contract is reused rather than restated** — the page
  bound, `has_more`, the threshold, the tie rule; they are the same and should
  read as the same.

## Blockers

None.
