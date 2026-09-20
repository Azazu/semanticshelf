# Design — add-embedder-protocol-and-clip

## Context

See `proposal.md` — Why. Current state: the schema stores a vector per model key and enforces its width; `app/domain.py` holds the registry of keys and widths; nothing produces a vector. Constraints: `make check` must stay green without a database and **without weights**, so no test in that suite may load a model; inference must not block the event loop (`AGENTS.md`); the specification fixes the keys, the widths and the setting names (§2.3). Verified on the installed package rather than assumed: `transformers` 5.17.0 exposes `CLIPModel` with `get_text_features` and `get_image_features`, plus `CLIPProcessor` and `AutoProcessor`; `openai/clip-vit-large-patch14` declares `projection_dim` 768 (read from its published configuration). Change 1 already declared the PyTorch CPU index and the `torch` source mapping, so the heavy dependency resolves to the CPU build without further work.

## Goals / Non-Goals

**Goals:** one protocol every model satisfies; a width knowable without loading; loading that happens once, late, and off the event loop; a deterministic stand-in good enough that the rest of the system never needs a model in tests; a readiness check that catches a schema and a registry that disagree.

**Non-Goals:** anything under Non-goals in the proposal; inference speed; model quality; batching strategy beyond a fixed size.

## Decisions

1. **The protocol is structural, not a base class.** `Embedder` is a `typing.Protocol` with `key`, `dim`, `embed_text` and `embed_images`. An adapter is any object that satisfies it, so the fake owes nothing to the real one and neither inherits behaviour it does not want. A shared conformance test parametrised over every embedder enforces the contract in one place; adding DINOv2 later means adding it to that parameter list.
2. **Vectors are `numpy` arrays, normalised by the protocol's own helper.** `float32`, shape `(n, dim)`, each row unit length. Normalisation lives in one function that every adapter calls, so "unit length" is a property of the contract rather than of each adapter's care. A zero vector — which normalisation cannot fix — is an error, not a silent `nan`.
3. **A model without a text tower raises rather than returns.** `embed_text` on such an adapter raises `TextNotSupportedError` naming the key. The alternative the specification mentions, returning `NotImplemented`, was rejected: a sentinel travels silently into a vector column, an exception cannot.
4. **The registry is a module-level cache behind one lock per process.** `get_embedder(key, settings)` returns the loaded adapter, loading it on first use while holding the lock, storing it only on success. A failure is not cached, so a transient download failure does not poison the process. Nothing is loaded at import or in the application factory; the lifespan loads only what `MODEL_WARMUP` names. A test hook clears the cache between tests.
5. **Inference runs on its own bounded pool**, a `ThreadPoolExecutor` of `INFERENCE_WORKERS` threads created by the lifespan and owned by the application, reached through one helper that awaits `loop.run_in_executor`. Starlette's shared threadpool was rejected: it also serves file reads, and a burst of embedding calls there would stall them. The worker process of a later change constructs the same pool without an application.
6. **The CLIP adapter loads through `AutoProcessor` and `CLIPModel`** with an explicit `cache_dir` from `MODEL_CACHE`, rather than by mutating `HF_HOME` in the process environment: an explicit argument is visible at the call site and cannot leak into anything else the process does. `HF_HUB_OFFLINE` keeps working because it is read by the hub library itself. Inference runs under `torch.inference_mode()`, in batches of `EMBED_BATCH_SIZE`, after `torch.set_num_threads(TORCH_NUM_THREADS)`.
7. **Truncation is detected by tokenising twice**, once without truncation to learn the true length and once with it, and reported per input. It costs one extra tokenisation of a string that is at most a few hundred characters, and it is the only way to tell the caller something was dropped; the search layer of change 8 puts that flag in its response.
8. **The fake derives vectors from a hash of its input**, not from a random seed drawn at construction: the same text gives the same vector in another process, which is what makes fixtures reproducible. Text and an image carrying the same token agree because the image path extracts that token from the image's own pixels is *not* possible — instead the fake reads the token from the image's `info` dictionary, which the test helper sets when it builds the image. That is honest: the fake models the *relationship* the real model has, it does not pretend to see.
9. **Readiness compares declarations, never weights.** The new `models` check reads the definition of the dimension constraint from the catalog and asserts that every enabled key appears in it with the width the application declares. It needs the database, so it is skipped exactly like the migration check when the database check fails, and it loads nothing — which is what keeps the probe cheap and what the health-probes spec demands.
10. **`models warm` is a `typer` application with one command.** The specification puts the command in this change and the rest of the CLI in change 7, so the entry point is created here with the single command and the console script; change 7 adds its commands to the same application. A throwaway `argparse` script that change 7 would rewrite was rejected as churn.
11. **CI caches the uv environment.** The dependency set gains the CPU build of torch; `enable-cache: true` on `astral-sh/setup-uv` restores it between runs. This is the one CI edit of the change, and the tier already accounts for it.
12. **Tests never load weights, and the rule is enforced rather than remembered.** The real-model tests live under `tests/models/` behind the `models` marker, `make test` and `make check` deselect it, and a unit test asserts that no module under `app/` imports `torch` or `transformers` at import time — the adapter imports them inside the load function. That keeps `make check` fast and keeps a stray top-level import from dragging a 200 MB dependency into every test run.

## Applicability (high tier)

| Question | Applies? | Note |
|---|---|---|
| Crash before/after an external effect | yes | The external effect is the weight download. It is the hub library's own cache write, which resumes and validates; our registry stores the adapter only after the load returns, so a crash mid-download leaves no half-registered model and the next attempt re-enters the same path. |
| Concurrent writers | yes | Concurrent first use of one key. One lock, one load, one shared instance; the test drives several threads at the same key and asserts the loader ran once. |
| Money rounding | n/a | |
| Empty/zero/null inputs | yes | Empty batch returns an empty array without touching the model; empty or whitespace-only text is embedded as given (the model has its own opinion) but a zero-norm vector is refused rather than normalised into `nan`; an image with no pixels is a decoding error, raised by the caller's decoder, not here. |
| Authorization boundary | yes | No authentication exists, but this change opens the service's only outbound connection. It goes to the Hugging Face Hub, only on first use of a key, only for the configured checkpoint, into `MODEL_CACHE`; `HF_HUB_OFFLINE=1` turns it off for an air-gapped host. Nothing else in the service makes a network call, and the how-to says so. |
| Deletion/expiry | n/a | The weight cache is the operator's to clear; nothing in the service deletes it. |
| Idempotency of retries | yes | Loading is idempotent: a second call returns the cached instance; a failed load is not cached, so a retry is a fresh attempt. Embedding is pure — the same input gives the same vector within a process. |

## Risks / Trade-offs

- [A stray top-level `import torch` makes every test run pull 200 MB] → decision 12: a unit test walks `app/` and fails on a top-level import of `torch` or `transformers`.
- [The first CI run after this change is slow] → the uv cache (decision 11); the first run pays, later runs restore.
- [`transformers` 5.x renames something between now and apply] → the API was read from the installed 5.17.0 source, and the dependency is pinned by `uv.lock`; a future bump is a reviewed diff that re-runs `make test-models`.
- [The fake's text-image relationship is a fiction] → stated plainly in decision 8 and in the module's docstring, so no later change mistakes it for evidence about real models.
- [Truncation detection tokenises twice] → bounded by the 256-character limit the specification puts on a query.

## Migration Plan

Apply on the branch; `make check` green with no weights present; `make test-models` run once locally to prove the real adapter (it downloads about 1.7 GB, so it is run deliberately, not in CI); user pushes; CI green; Gate 2; merge. Rollback: revert the merge commit; the weight cache under `MODEL_CACHE` is inert data and can be deleted by hand.

## Open Questions

None.
