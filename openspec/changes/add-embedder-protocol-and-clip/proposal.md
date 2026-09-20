# Proposal — add-embedder-protocol-and-clip

**Risk-Tier:** high

Tier rationale: the CLIP adapter downloads model weights from the Hugging Face Hub on first use, which is the "model downloads and any network egress from the service" trigger of `AGENTS.md`. The change also edits `.github/workflows/ci.yml` to cache the uv environment, because the new dependency set is large. Both are `high` triggers on their own.

## Why

The schema can store a vector per model, and nothing can produce one. Every remaining feature depends on this piece: upload enqueues extraction, the worker runs it, search embeds a query. The decisions that are expensive to revise later are made here — what an embedder is, when weights load, which thread runs inference, and how tests get vectors without ever touching a model.

## What Changes

1. **The `Embedder` protocol** (`app/ml/base.py`): a stable `key`, a `dim` known without loading anything, `embed_text` and `embed_images` returning L2-normalised `float32` vectors of that width. A model without a text tower says so rather than returning a wrong vector.
2. **A lazy per-process registry** (`app/ml/registry.py`): nothing loads at import or at application start; the first caller that needs a key pays the load, once, under a lock, even when several callers arrive together. A failed load is not cached, so a retry can succeed. `MODEL_WARMUP` lists keys the lifespan loads deliberately.
3. **A dedicated, bounded inference threadpool** (`INFERENCE_WORKERS`, default 2), created by the lifespan and owned by the application: inference never runs on the event loop, and a burst of embedding calls cannot starve the ordinary threadpool that serves file reads.
4. **The CLIP adapter** (`app/ml/clip.py`): `CLIPModel` with both towers through `transformers` 5.17 on CPU, batched, under `torch.inference_mode()`, weights cached in `MODEL_CACHE`, `HF_HUB_OFFLINE` honoured. A query longer than the model's context is truncated and the caller is told, so the search layer can say so in its response.
5. **The deterministic fake** (`app/ml/fake.py`): unit vectors derived from a hash of the input, no torch, no weights. Text and the image of the same token land near each other, so later changes can test ordering, thresholds and model isolation without a model. One shared conformance test runs against every embedder, fake and real alike.
6. **Readiness gains a third check** (FR-MDL-7): every enabled model key is declared by the database's dimension constraint with the width the application declares. It compares declarations and loads nothing, so the probe stays as cheap as it was.
7. **`models warm`**: a small `typer` entry point that loads the enabled models once, printing each key, width and load time. It exists so an image build or an air-gapped host can fill the cache deliberately instead of paying for it on the first request. The folder-indexing change extends the same application with its own commands.
8. **On-demand real-model tests** (`tests/models/`, marker `models`, `make test-models`): loads CLIP once, asserts the width is 768 and the vectors are unit length. Never part of `make check` and never part of CI.
9. **CI caches the uv environment** (`enable-cache: true` on `astral-sh/setup-uv`): the dependency set grows by the CPU build of torch and its neighbours, and re-downloading it on every run is waste.
10. **Settings and documentation**: `ENABLED_MODELS`, `MODEL_WARMUP`, `MODEL_CACHE`, `CLIP_MODEL_NAME`, `DEVICE`, `TORCH_NUM_THREADS`, `EMBED_BATCH_SIZE`, `INFERENCE_WORKERS`, each with a default, so no new variable is required and the environment template needs no edit.

## Capabilities

### New Capabilities

- `embedding-models`: what an embedder guarantees — a width known without loading, unit-length vectors, one load per process, truncation reported rather than hidden, a deterministic stand-in for tests, and inference that never blocks the event loop.

### Modified Capabilities

- `health-probes`: the readiness probe gains the model-declaration check and reports it as a third entry in `checks`.

## Non-goals

- No DINOv2: the second adapter, the image-to-image surface and the `model` parameter are `add-dinov2-image-search` (change 11). The protocol is written so it needs no change to accept it.
- No HTTP endpoint that embeds anything: search is change 8. Nothing in this change is reachable from the network except the readiness probe's new line.
- No extraction pipeline: enqueueing, claiming and writing vectors are changes 6 and 13. This change produces vectors; nothing yet stores them.
- No GPU support, no quantisation, no ONNX, no batching strategy beyond a fixed batch size: CPU inference with the defaults, measured later if it hurts.
- No recall or latency numbers: `tune-vector-indexes` (change 14) owns measurement. This change asserts shape and determinism, not quality.
- No multilingual text tower: CLIP is English-only and the specification says so; lifting it is a stretch change.
- No edit to the environment template: every new setting has a default.

## Impact

- New: `app/ml/{__init__,base,registry,clip,fake,pool}.py`, `app/cli.py`, `tests/unit/test_embedder_protocol.py`, `tests/unit/test_registry.py`, `tests/unit/test_fake_embedder.py`, `tests/api/test_readiness_models.py`, `tests/models/{__init__,test_clip.py}`, `docs/how-to/models.md`.
- Modified: `pyproject.toml` and `uv.lock` (dependencies, the `models` marker, the console script), `app/core/settings.py` (eight settings), `app/main.py` (the pool in the lifespan), `app/services/readiness.py` and `app/api/health.py` (the third check), `Makefile` (`test-models`), `.github/workflows/ci.yml` (uv cache), `docs/reference/settings.md`, `docs/reference/commands.md`, `AGENTS.md` (layout gains `ml/` and `cli.py`).
- New runtime dependencies, each justified against the anti-overengineering rule: `transformers` (the CLIP implementation and its processor; writing one is not a portfolio exercise), `torch` (what `transformers` runs on; the CPU build through the index change 1 already declared), `numpy` (the vector interchange type the protocol returns, already a transitive dependency but imported directly), `pillow` (the image type `embed_images` accepts, and the decoder change 5 will use), `typer` (the console entry point the specification fixes for this change and extends in change 7).
- CI runtime grows by the first uncached dependency sync; the cache makes later runs cheap.
