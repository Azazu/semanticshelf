## 1. Dependencies and settings

- [x] 1.1 Add the runtime dependencies with `uv add transformers torch numpy pillow typer` and commit the lock; confirm the CPU build was chosen. Verify: `make lock-check` exits 0 and `uv run python -c 'import torch; print(torch.__version__, torch.cuda.is_available())'` prints a `+cpu` build and `False`.
- [x] 1.2 Extend `app/core/settings.py` with the seven settings of the proposal's table and exactly those defaults: `enabled_models` = every key the build implements (`clip-vit-l14`), `model_warmup` = empty, `model_cache` = `.data/models`, `clip_model_name` = `openai/clip-vit-large-patch14`, `torch_num_threads` = 0 (torch's own choice), `embed_batch_size` = 8, `inference_workers` = 2; plus a validator that rejects an enabled or warm-up key the service does not implement. There is no `device` setting. Verify: `tests/unit/test_settings_models.py` asserts each default by value, that the default configuration starts, that an unknown key is rejected naming the offender, and that a warm-up key outside the enabled set is rejected.
- [x] 1.3 Register the `models` pytest marker and keep it out of the gate floor: `make test` deselects both `integration` and `models`. Verify: `make test` collects neither marked suite, and `uv run pytest -m models --collect-only` lists the real-model tests.

## 2. The protocol, normalisation and the deterministic embedder

- [x] 2.1 Write `app/ml/base.py`: the `Embedder` protocol (`key`, `dim`, `embed_text`, `embed_images`), the `EmbeddingResult` carrying vectors and the truncation flags, `TextNotSupportedError`, and the normalisation helper that returns `float32` unit rows and refuses a zero-norm row. Verify: unit tests for the helper cover a plain vector, an already-normalised vector, a batch, and the zero vector that must raise.
- [x] 2.2 Write `app/ml/fake.py`: deterministic vectors from a hash of the input, no torch import, text and an image carrying the same label landing near each other, plus an image-only variant for testing the refusal. Verify: `tests/unit/test_fake_embedder.py` covers determinism across processes (the vector of a fixed input is compared with a constant recorded in the test), distinctness, the text-image relationship, and the refusal.
- [x] 2.3 Write the shared conformance test parametrised over every available embedder (`tests/unit/test_embedder_protocol.py`): width, dtype, unit length, batch order, empty batch. Verify: it passes for both fake variants and is written so that adding an embedder means adding one parameter.

## 3. Registry and inference pool

- [x] 3.1 Write `app/ml/registry.py`: lazy per-process cache behind one lock, storing only on success, with a hook that clears it for tests. Verify: `tests/unit/test_registry.py` asserts nothing is loaded until asked, that several threads asking at once load once, and that a failing load is not remembered.
- [x] 3.2 Write `app/ml/pool.py` and wire it into the lifespan: a `ThreadPoolExecutor` of `inference_workers` threads owned by the application, one helper that runs a callable on it, the asynchronous `acquire(key)` that obtains an embedder through that helper (design decision 5), and shutdown with the application. Verify: unit tests show that work submitted through the helper runs on a different thread, that other tasks on the event loop keep progressing while a slow embed is in flight, and that they keep progressing while a slow *load* is in flight.
- [x] 3.3 Warm-up: the lifespan loads exactly the keys `MODEL_WARMUP` names, through the pool rather than on the loop, and nothing else. Verify: an api test with a fake registry asserts that an empty warm-up list loads nothing, that a named key is loaded once at startup, and that the load ran on a pool thread rather than the one running the loop.

## 4. The CLIP adapter

- [x] 4.1 Write `app/ml/clip.py`: `AutoProcessor` and `CLIPModel` loaded with an explicit cache directory, both towers, batching, `torch.inference_mode()`, `torch.set_num_threads` only when the setting is positive, truncation detected by tokenising with and without truncation, and imports of `torch` and `transformers` inside the load function rather than at module level. Verify: `make types` and `make lint` green, and the import test of task 7.4 passes.
- [x] 4.1a Add the checkpoint guard (design decision 13): after loading, compare the width the checkpoint produces with the width the key declares and raise `CheckpointWidthError` naming the key and both widths on a mismatch. Verify: a unit test of the comparison covers a fitting width, a wider one and a narrower one; the real-model test of task 4.2 exercises the fitting path.
- [x] 4.2 Write `tests/models/test_clip.py` behind the `models` marker: load the real model once, assert the key, the width of 768, unit length for text and for an image, batch order, and that a long text reports truncation. Verify: `make test-models` passes locally once, with the weight download recorded in the commit body; it is not part of `make check` or CI.

## 5. Readiness

- [x] 5.1 Add the `models` check to `app/services/readiness.py` and the third entry to the probe: read the dimension constraint from the catalog, compare every enabled key and width against it, skip when the database check failed, load nothing. The check covers an application and a schema that disagree, not a wrong checkpoint, which task 4.1a owns. Verify: unit tests of the comparison with stubbed constraint text, and an integration test that a consistent database reports `ok`.
- [x] 5.2 Update the readiness tests that assert the exact `checks` body so they expect three entries. Verify: `make check` and `make test-integration` green.

## 6. Warm-up command and documentation

- [x] 6.1 Write `app/cli.py`: a `typer` application with `models warm`, loading each enabled model and printing its key, width and load time; register the console script in `pyproject.toml`. Verify: `uv run semanticshelf models warm --help` prints the command's help without loading anything, recorded in the commit body.
- [x] 6.2 Add the `test-models` target to the `Makefile`. Verify: `make help` lists it and `make test-models` runs only the marked suite.
- [x] 6.3 Write `docs/how-to/models.md` (what is downloaded, where it goes, how much it weighs, how to warm it up, how to run offline) and extend `docs/reference/settings.md` with the seven settings, `docs/reference/commands.md` with the new target and command, and the `AGENTS.md` layout with `ml/` and `cli.py`. Verify: re-read all four whole; every command in them was run in its exact form.

## 7. Failing inputs (high tier: one per new or changed check)

- [x] 7.1 Settings guard: a configuration naming an unimplemented model key makes the application refuse to start with that key in the message. Verify: output recorded in the commit body.
- [x] 7.2 Conformance test: an embedder variant that returns a wrong width, and one that returns an unnormalised vector, each fail the shared conformance test. Verify: both outputs recorded, variants removed.
- [x] 7.3 Registry: with the success-store removed, the "load once under concurrency" test fails. Verify: output recorded, code restored.
- [x] 7.4 Import discipline: a temporary top-level `import torch` in a module under `app/` fails the import test. Verify: output recorded, import removed, `git status --short` clean.
- [x] 7.5 Readiness: enabling a model key the schema does not declare makes `/ready` answer 503 with `checks.models` naming the key and the widths, and no model loaded. Verify: this is a test, not a probe — output recorded in the commit body.
- [x] 7.6 Event loop, inference: running the embed call inline instead of through the pool fails the progress test. Verify: output recorded, code restored.
- [x] 7.7 Event loop, loading: obtaining an embedder synchronously on the loop instead of through `acquire` fails the load-progress test. Verify: output recorded, code restored.
- [x] 7.8 Checkpoint guard: a declared width that disagrees with the loaded checkpoint's width raises `CheckpointWidthError` naming the key and both numbers. Verify: output recorded (a unit test, so no second download).

## 8. Specification amendments

- [x] 8.1 Amend `docs/explanation/requirements.md` as the proposal's item 12 states: FR-IDX-1's default for `ENABLED_MODELS` becomes the keys the build implements; FR-MDL-4 drops the `DEVICE` setting and states CPU inference once, consistent with §10; FR-MDL-7 splits into the readiness comparison and the adapter's checkpoint guard. Verify: re-read §2.3 and §2.4 whole; `rg -n 'DEVICE' docs/ app/ openspec/specs/` returns nothing outside this change's own history, and no artifact still claims the probe catches a wrong checkpoint.

## 9. CI

- [ ] 9.1 Add `enable-cache: true` to the `astral-sh/setup-uv` step in `.github/workflows/ci.yml`. Verify: the pinned actionlint image exits 0 over the workflow, and the user's run on the branch is green.

## 10. Wrap-up

- [ ] 10.1 Commits per block without agent trailers, each body naming the evidence of the tasks whose diff it holds. Verify: `git log --format=%B main..HEAD | grep -c '^Co-Authored-By'` prints `0`.
- [ ] 10.2 `make check` green with no weights present (`env -u DATABASE_URL make check`), `make test-integration` green against pgvector, `make test-models` green once locally. Verify: all three outputs recorded in the commit bodies.
- [ ] 10.3 Acceptance on GitHub (user pushes the branch): `workflow` green and `python` green, with the uv cache in place and no model download in the run. Verify: the user reports the run.
- [ ] 10.4 `openspec validate add-embedder-protocol-and-clip --strict` and `scripts/pregate-verify.sh gate2 add-embedder-protocol-and-clip` pass; request Gate 2 with `/gate-review add-embedder-protocol-and-clip 2`.
