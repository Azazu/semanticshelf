# Design — add-dinov2-image-search

## Context

See `proposal.md` — Why. What the design has to work with:

- **The schema is ready and was checked, not assumed.** The live constraint
  reads `((model = 'clip-vit-l14' AND vector_dims(vector) = 768) OR (model =
  'dinov2-large' AND vector_dims(vector) = 1024))` and the indexes are
  `ix_embeddings_clip_vit_l14` and `ix_embeddings_dinov2_large` — change 3 wrote
  both. This change fills the second index; it migrates nothing.
- `app/domain.py` already declares `DINOV2_LARGE` and its width; only
  `IMPLEMENTED_MODELS` does not name it yet, and `ENABLED_MODELS` defaults to
  every implemented key (FR-IDX-1).
- The search service of change 8 owns the bounds — the page maximum, the depth
  that ends at 999, the effort per query, the threshold, the tie rule — and the
  repository's `nearest` takes a model, a vector, a page and a maximum distance.
- The upload pipeline can already decode and refuse a picture without storing
  it: the folder import's dry run does exactly that (`examine_one`), writing to
  a temporary file outside the media root and discarding it in a `finally`.
- `app/ml/base.py` normalises and checks every vector, so the new adapter is
  responsible for producing features and nothing else.

## Goals / Non-Goals

Goals beyond the proposal's scope statement:

- A picture as a query costs one inference and leaves nothing behind.
- `/similar` costs no inference at all — the vector is already stored.
- Everything about a page (its bounds, its order, its refusals) is the same for
  both kinds of query, because it is the same code.

Non-goals at the design level: filtered vector search (change 12), any measure
of which model is better (change 14), and any change to how vectors are stored.

## Decisions

1. **The adapter produces the CLS token after the final layer norm, and nothing
   else.** `facebook/dinov2-large` through `transformers`, image-only: it raises
   `TextNotSupportedError` from `embed_text`, which is what the
   `embedding-models` capability already requires of a model with no text tower.
   The width (1024) is declared in `app/domain.py` and checked at load by the
   guard change 4 wrote, so a checkpoint of another size is refused rather than
   stored. Which attribute carries the CLS token is read from the installed
   `transformers` at implementation, not assumed here.
   Rejected: mean-pooling the patch tokens — a different vector space than the
   one the width and the literature describe, and a silent one.

2. **A model says what it can be asked, in one place.** `app/domain.py` gains a
   small table: which keys have a text side, which have an image side. The
   router consults it to refuse — 503 for a key this build does not run (the
   refusal change 8 already gives), 422 for a key that cannot take that kind of
   query — and the service never sees an impossible pair. One table, because
   two places would drift the day a third model arrives.
   Rejected: asking the embedder — that would load the model to find out what it
   cannot do.

3. **The query picture is decoded like an upload and dropped like a dry run.**
   The bytes are streamed to a temporary file outside the media root, inspected
   by `images.inspect` (the same refusals, the same caps, the same problem
   details), opened for inference and unlinked in a `finally` — the path
   `examine_one` established. Nothing under the media root, no asset row, no
   hash lookup: a search is not an upload that forgot to save.

4. **`/similar` reads the vector rather than making one.** The asset's stored
   vector for the search model is the query; when there is none, the answer is
   409 before anything is searched. No model is loaded, which is also what makes
   the endpoint answerable on a build whose weights were never downloaded.

5. **The asset is excluded by asking for one more and dropping it.** The
   vector query asks for `limit + 1 + 1` rows — one for `has_more`, one for the
   asset itself, which is always the nearest to its own vector — and the service
   drops the asset by identifier. A `WHERE asset_id <> …` inside the ordered
   select would be a filter on an approximate index scan: the same class of
   problem change 12 exists to measure, for one row that is trivially known.
   Rejected: dropping it after the page is cut — that would silently shorten the
   first page by one.

6. **`index missing` is one statement and then the ordinary drain.**
   `INSERT INTO indexing_jobs (asset_id, model) SELECT a.id, :model FROM assets a
   WHERE NOT EXISTS (a vector for that model) AND NOT EXISTS (unfinished work
   for that model) ON CONFLICT DO NOTHING`, then the same
   claim/execute/finish drain `index-folder` uses. Two runs at once cannot
   double-queue: the unique constraint the queue already carries decides, and
   `ON CONFLICT DO NOTHING` makes that a no-op rather than an error.
   Rejected: queueing at start-up or in the lifespan — the service would begin
   writing rows and burning CPU because someone restarted it, and nothing in
   this service writes without being asked.

7. **The interface's fifth page is the search page with a different question.**
   Same grid, same scores, same "More", same refusal surface; what differs is
   what it sends — a chosen file, or an asset's identifier reached from the
   "similar" action on any thumbnail. The action lives in the shared grid, so
   Browse and Search both get it for free.

8. **`make demo` ends with `index missing`.** The corpus is imported by a
   command that queues what an upload queues, so a corpus imported before this
   change has no DINOv2 vector; the demo has to end usable for both searches,
   and one command says so.

## Applicability

| Question | Answer |
|---|---|
| Crash around an external effect | The query picture is written to a temporary file outside the media root and unlinked in a `finally`; a crash between the two leaves a file in the system temporary directory and nothing in the store — no asset, no vector, no work. The backfill's insert is one statement in one transaction: it either queued the work or it did not. |
| Concurrent writers | Two backfills at once cannot double-queue: the queue's unique constraint decides and `ON CONFLICT DO NOTHING` makes the loser a no-op. Two runners taking that work is the claim the queue already answers (`FOR UPDATE SKIP LOCKED`, ADR-003). A search never writes. |
| Empty / zero / null inputs | A store with no vectors for the search model answers an empty page; an asset with no vector for it answers 409 rather than an empty page, because "nothing is known" is not "nothing is like it"; a picture that decodes to nothing acceptable is the upload's own refusal; a corpus where every asset already has its vector makes `index missing` a no-op that says so. |
| Idempotent retries | Searching the same picture twice costs two inferences and changes nothing. Asking for the missing work twice queues nothing the second time. A retried job is the queue's existing at-least-once upsert. |
| Deletion / expiry | An asset deleted between being listed and having its neighbours asked for answers 404, as every other read of it does; its work and vectors went with it (change 6). Nothing here deletes. |
| Authorization boundary | n/a — the service has no authentication (D12), and this change adds no privileged operation: the backfill is a CLI command, like every other operator action. |
| Money rounding | n/a. |

## Risks / Trade-offs

- **A second model doubles what an upload costs** in CPU and, on a cold cache,
  adds ~1.2 GB of weights → it is what FR-IDX-1's default means, the how-to
  says so before the first `make demo`, and `ENABLED_MODELS` still lets a
  deployment run one model.
- **`/similar` on a large store reads one extra row per page** → trivially
  bounded, and it buys a self-exclusion that cannot silently shorten a page.
- **The backfill drains in the foreground** like `index-folder` → it is an
  operator command with a progress bar, and `--no-index` leaves the work queued
  for the worker of change 13.
- **Two models make `index_status` two-valued** → the API already answers a map
  per model and the interface already renders it; what changes is that it stops
  having exactly one key, which the demo corpus will show immediately.

## Migration Plan

None. No schema change, no data change: the constraint and both indexes have
been in place since change 3, and this change writes rows of the kind they were
built for. A deployment that keeps `ENABLED_MODELS=clip-vit-l14` sees no
difference at all.

## Open Questions

None.
