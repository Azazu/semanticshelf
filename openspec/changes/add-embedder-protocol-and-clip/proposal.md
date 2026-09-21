# Proposal — add-embedder-protocol-and-clip

**Risk-Tier:** high

Tier rationale: the CLIP adapter downloads model weights from the Hugging Face Hub on first use, which is the "model downloads and any network egress from the service" trigger of `AGENTS.md`. The change also edits `.github/workflows/ci.yml` to cache the uv environment, because the new dependency set is large. Both are `high` triggers on their own.

## Why

The schema can store a vector per model, and nothing can produce one. Every remaining feature depends on this piece: upload enqueues extraction, the worker runs it, search embeds a query. The decisions that are expensive to revise later are made here — what an embedder is, when weights load, which thread runs the load and the inference, and how tests get vectors without ever touching a model.

## What Changes

1. **The `Embedder` protocol** (`app/ml/base.py`): a stable `key`, a `dim` known without loading anything, `embed_text` and `embed_images` returning L2-normalised `float32` vectors of that width. A model without a text tower raises rather than returning a wrong vector.
2. **A lazy per-process registry** (`app/ml/registry.py`): nothing loads at import or at application start; the first caller that needs a key pays the load, once, under a lock, even when several callers arrive together. A failed load is not cached, so a retry can succeed.
3. **Loading and inference both run on a dedicated, bounded pool** (`INFERENCE_WORKERS`, default 2), created by the lifespan and owned by the application. A multi-gigabyte load is work like any other: the async path obtains an embedder through the pool, so neither the first request nor the warm-up blocks the event loop. The synchronous entry point stays for the worker process of a later change.
4. **The CLIP adapter** (`app/ml/clip.py`): `CLIPModel` with both towers through `transformers` 5.17 on CPU, batched, under `torch.inference_mode()`, weights cached in `MODEL_CACHE`, `HF_HUB_OFFLINE` honoured. A query longer than the model's context is truncated and the caller is told, so the search layer can pass that on.
5. **A checkpoint that does not fit its key is refused at load.** The adapter reads the width the loaded checkpoint actually produces and compares it with the width its key declares; a mismatch raises and no vector is produced. This is where a wrong `CLIP_MODEL_NAME` is caught — before anything can be written — because a probe that only compares declarations cannot see inside a checkpoint.
6. **The deterministic fake** (`app/ml/fake.py`): unit vectors derived from a hash of the input, no torch, no weights. Text and the image of the same token land near each other, so later changes can test ordering, thresholds and model isolation without a model. One shared conformance test runs against every embedder, fake and real alike.
7. **Readiness gains a third check**: every enabled model key is declared by the database's dimension constraint with the width the application declares. It compares declarations and loads nothing, so the probe stays as cheap as it was. It catches an application and a schema that disagree; it does not and cannot catch a wrong checkpoint, which is item 5's job.
8. **`models warm`**: a small `typer` entry point that loads the enabled models once, printing each key, width and load time, so an image build or an air-gapped host can fill the cache deliberately. The folder-indexing change extends the same application.
9. **On-demand real-model tests** (`tests/models/`, marker `models`, `make test-models`): loads CLIP once, asserts the width is 768, the vectors are unit length and a long text reports truncation. Never part of `make check` and never part of CI.
10. **CI caches the uv environment** (`enable-cache: true` on `astral-sh/setup-uv`).
11. **Settings**, all with defaults, so no new variable is required and the environment template needs no edit:

    | Setting | Default | What it decides |
    |---|---|---|
    | `ENABLED_MODELS` | every key the service implements — `clip-vit-l14` in this change, both once the DINOv2 adapter lands | which models the service offers |
    | `MODEL_WARMUP` | empty | which of them the lifespan loads at start |
    | `MODEL_CACHE` | `.data/models` | where weights are cached |
    | `CLIP_MODEL_NAME` | `openai/clip-vit-large-patch14` | the checkpoint behind the `clip-vit-l14` key |
    | `TORCH_NUM_THREADS` | `0`, meaning torch's own default of one thread per physical core | inference threads inside torch |
    | `EMBED_BATCH_SIZE` | `8` | inputs per forward pass |
    | `INFERENCE_WORKERS` | `2` | threads in the loading and inference pool |

12. **Three amendments to the specification**, each because the artifacts and the code would otherwise contradict it:
    - **FR-IDX-1**: `ENABLED_MODELS` defaults to *the keys the service implements*, not to both, so the default configuration starts on a build where only CLIP exists. The DINOv2 change adds its key to the implementation and to the default in one step.
    - **FR-MDL-4**: the `DEVICE` setting is dropped. §10 already makes GPU support a non-goal, so a setting whose only tested value is `cpu` promises something nobody ran; inference is CPU, stated once.
    - **FR-MDL-7**: split into the two guarantees that are actually achievable — the readiness probe compares the application's registry with the schema, and an adapter refuses a checkpoint whose width differs from its key's declared width at load time, before any vector exists.

## Capabilities

### New Capabilities

- `embedding-models`: what an embedder guarantees — a width known without loading, unit-length vectors, one load per process, a checkpoint that must fit its key, truncation reported rather than hidden, a deterministic stand-in for tests, and loading and inference that never block the event loop.

### Modified Capabilities

- `health-probes`: the readiness probe gains the model-declaration check and reports it as a third entry in `checks`.

## Non-goals

- No DINOv2: the second adapter, the image-to-image surface and the `model` parameter are `add-dinov2-image-search` (change 11). The protocol is written so it needs no change to accept it, and that change also extends the default of `ENABLED_MODELS`.
- No GPU: inference is CPU, and the `DEVICE` setting the specification used to name is removed rather than left as an untested promise (item 12).
- No HTTP endpoint that embeds anything: search is change 8. Nothing here is reachable from the network except the readiness probe's new line.
- No extraction pipeline: enqueueing, claiming and writing vectors are changes 6 and 13. This change produces vectors; nothing yet stores them.
- No quantisation, no ONNX, no batching strategy beyond a fixed size, no recall or latency numbers: `tune-vector-indexes` (change 14) owns measurement. This change asserts shape, determinism and refusal, not quality.
- No multilingual text tower: CLIP is English-only and the specification says so; lifting it is a stretch change.
- No edit to the environment template: every new setting has a default.

## Impact

- New: `app/ml/{__init__,base,registry,clip,fake,pool}.py`, `app/cli.py`, `tests/unit/{test_embedder_protocol,test_registry,test_fake_embedder,test_settings_models}.py`, `tests/api/test_readiness_models.py`, `tests/models/{__init__,test_clip}.py`, `docs/how-to/models.md`.
- Modified: `pyproject.toml` and `uv.lock` (dependencies, the `models` marker, the console script), `app/core/settings.py` (seven settings), `app/main.py` (the pool in the lifespan, warm-up through it), `app/services/readiness.py` and `app/api/health.py` (the third check), `Makefile` (`test-models`, and `test` deselecting the new marker), `.github/workflows/ci.yml` (uv cache), `docs/explanation/requirements.md` (the three amendments), `docs/reference/settings.md`, `docs/reference/commands.md`, `AGENTS.md` (layout gains `ml/` and `cli.py`).
- New runtime dependencies, each justified against the anti-overengineering rule: `transformers` (the CLIP implementation and its processor; writing one is not a portfolio exercise), `torch` (what `transformers` runs on; the CPU build through the index change 1 already declared), `numpy` (the vector interchange type the protocol returns, already transitive but imported directly), `pillow` (the image type `embed_images` accepts, and the decoder change 5 will use), `typer` (the console entry point the specification fixes for this change and extends in change 7).
- CI runtime grows by the first uncached dependency sync; the cache makes later runs cheap.
