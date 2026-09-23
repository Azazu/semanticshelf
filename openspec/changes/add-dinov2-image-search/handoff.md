# Handoff — add-dinov2-image-search

**Updated:** 2026-09-23 · claude
**State:** proposing
**Branch:** change/add-dinov2-image-search
**Security-sensitive:** yes — a picture arrives in a request body and is
decoded (FR-IMG-1), a second model is downloaded and loaded on first use, and
the API's search surface gains a parameter a client chooses. `AGENTS.md` puts
file uploads and model downloads at `high`; the roadmap already declared it.

## Done this session

Branch, scaffold and all four planning artifacts. One decision the user made
before anything was written: **the backfill is an operator command**
(`index missing`), not something the service does at start — existing assets
have no DINOv2 vector, a second `make demo` gives them none (the import sees
duplicates and queues nothing), and a demo where "find similar" answers 409 for
every picture is not a demo.

Two things checked rather than assumed, and both changed the plan:

- **No migration is needed.** The live constraint already reads
  `(clip-vit-l14 AND 768) OR (dinov2-large AND 1024)` and both partial HNSW
  indexes exist — change 3 wrote them. The handoff written at `/workflow:start`
  said this change would need a migration; it does not, and the proposal's
  non-goals say so.
- **`embedding-models` needs no delta.** Its requirements are already written
  for any embedder, including "an embedder without a text tower refuses text",
  which is exactly what the new adapter must do. The proposal listed it as
  modified and no longer does.

## Next step

Gate 1, because the tier is `high`: `/gate-review add-dinov2-image-search 1`.
The mechanical floor already passes.

Worth the reviewer's attention: the model-choice rule lives in `text-search`
(the capability that already owns "a query is answered by the vectors of one
model") and `image-search` references it rather than restating it; and the
self-exclusion of `/similar` is done by asking for one row more rather than by a
predicate inside the ordered select, because a filter on an approximate index
scan is change 12's question.

## Blockers

None.
