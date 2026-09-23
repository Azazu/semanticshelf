# A picture as the question

**Risk-Tier:** high

The roadmap says so and three separate rules agree: a second model is
downloaded on first use (§Security-Sensitive Code names model downloads and
dependencies), a picture arrives in a request body and is decoded, and the
API's search surface grows a parameter a client chooses. Gate 1 on the
artifacts, Gate 2 on the code, an applicability table, and a demonstrated
failing input for every new check.

## Why

The store has held two kinds of answer since change 3 — the schema's CHECK
already names `dinov2-large` at 1024 dimensions and its partial HNSW index has
been sitting there empty ever since. Half the point of the project is the
comparison: CLIP answers "what is this picture *about*", DINOv2 answers "what
looks like this one", and a portfolio that only does the first is a portfolio
that only tells half the story.

It also finishes what change 10 deliberately left: FR-UI-1 names five pages and
the interface has four.

## What Changes

- **A DINOv2 adapter** behind the `Embedder` protocol
  (`facebook/dinov2-large`, 1024 dimensions, the CLS token after the final
  layer norm), image-only: it raises `TextNotSupportedError` for text rather
  than returning something a caller could store. It joins `IMPLEMENTED_MODELS`,
  which by FR-IDX-1 makes it enabled by default — **so every new asset is
  queued for both models**, and the weights (~1.2 GB) are downloaded on first
  use like CLIP's.
- **`POST /api/v1/search/image`**: a picture in a multipart body, decoded under
  the upload rules and **never stored**, embedded with the search model, and
  answered with the same envelope `GET /search/text` uses.
- **`GET /api/v1/assets/{id}/similar`**: the asset's own stored vector as the
  query — no inference at all — excluding itself, and 409 `not-indexed` when it
  has no vector for that model yet.
- **A `model` parameter on all three searches** (FR-IMG-4). The model decides
  what it can be asked: a text query needs a text tower, a picture needs an
  image tower, and a combination that does not exist is 422 rather than a
  silent fallback. Cross-model comparison stays impossible by construction —
  the query is embedded by the model whose vectors are searched.
- **`semanticshelf index missing [--model KEY]`**: queue the work an asset does
  not have yet and carry it out, the way `index-folder` finishes what it
  created. Existing assets have no DINOv2 vector, a second `make demo` will not
  give them one (the import sees duplicates and queues nothing), and a demo
  where "find similar" answers 409 for every picture is not a demo. `make demo`
  ends with it.
- **The "Find similar" page** in the interface: a picture to upload, or the
  "similar" action from any thumbnail, with the same grid, scores and paging
  the search page has.
- **Documentation**: `docs/how-to/searching.md` gains the second kind of
  search, and the two are compared where a reader will ask — what each is good
  at, and why a score from one says nothing about the other.

## Non-goals

- **Any change to the schema.** The CHECK constraint and both partial HNSW
  indexes were written in change 3 (ADR-001); this change fills the second one,
  it does not migrate anything.
- **Tag and metadata filters** on the new endpoints. FR-IMG-2 lists them, and
  FR-FLT-2 puts them inside the vector query, which is change 12's question
  with its own measurement. The new endpoints take the same page, threshold and
  model parameters as `/search/text` and no filters, exactly as `/search/text`
  has none today.
- **Measuring which model is better at what.** ADR-002 and change 14 own recall
  and latency; this change states what each model is for and leaves the numbers
  to the change that measures them.
- **A third model, or a model registry a client can extend.** `model` selects
  among the keys this build implements, and an unknown key is refused.
- **Re-embedding anything that already has a vector.** `index missing` queues
  what is missing; replacing an existing vector stays `POST /assets/{id}/reindex`.

## Capabilities

### New Capabilities

- `image-search`: the second kind of question — a picture as the query, from a
  request body or from an asset already stored; what is refused; what is never
  kept.

### Modified Capabilities

- `text-search`: the search surface gains a `model` parameter, and the rule
  that a model must be able to take the kind of query it is asked. The rule
  lives there because that capability already owns "a query is answered by the
  vectors of one model"; `image-search` references it rather than restating it.
  `embedding-models` needs no delta at all: its requirements are already written
  for any embedder, including the one about a model with no text tower refusing
  text — which is exactly what the new adapter does.
- `indexing-jobs`: work can be queued for what is missing, not only for what is
  new.
- `demo-ui`: the fifth page, and the "similar" action on a thumbnail.

## Impact

- New: `app/ml/dinov2.py`, `app/api/search.py` gains two endpoints (or a
  sibling module), `app/services/search.py` gains the image query and the
  by-asset query, `ui/pages/similar.py`, `tests/models/test_dinov2.py`.
- Changed: `app/domain.py` (`IMPLEMENTED_MODELS`), `app/ml/registry.py` (the
  second factory), `app/repositories/embeddings.py` (exclude an asset from its
  own neighbours), `app/cli.py` (`index missing`), `Makefile` (`make demo`
  ends with it), `docs/how-to/searching.md`, `docs/reference/settings.md`
  (`DINOV2_MODEL_NAME`), `docs/explanation/requirements.md` if anything here
  contradicts it.
- Unchanged: the schema, every migration, the queue's mechanism, the upload
  path. The storage rules are untouched: the query picture is decoded and
  dropped.
- No new dependency: `transformers` and `torch` already carry DINOv2.
