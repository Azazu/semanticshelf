# Tasks — stretch-style-search

## 1. The corpus that can be built rather than found

- [ ] 1.1 `scripts/style_corpus.py` (or the same module inside the benchmark):
  the deterministic looks of design decision 1 — plain, grayscale, posterise,
  edges, painterly, sepia — each a pure function of the bytes, applied to every
  picture of a named folder. Verify: unit tests that each look is deterministic
  (the same input twice gives identical bytes), that it produces a picture of
  the same size, and that a look which would return a blank image is refused
  rather than measured.
- [ ] 1.2 The corpus refuses to be too small to mean anything: at least 20
  photographs and at least 4 looks, or the run reports that and measures
  nothing (design decision 2's "four pictures decide nothing", made mechanical).
  Verify: unit tests for both bounds, each watched to refuse.

## 2. The measurement

- [ ] 2.1 `pyproject.toml`: `open_clip_torch` in a dependency **group of its
  own** (`style`), never in the runtime group, and `uv.lock` updated with
  `uv add --group style open_clip_torch`. Verify: `make lock-check` green;
  `tests/unit/test_image_definition.py` still proves the service image does not
  carry it; the layering test still proves `app/` imports nothing from
  `scripts/`.
- [ ] 2.2 The candidate's loader in `scripts/`: `open_clip`'s `ViT-L-14` visual
  tower with `visual.proj` removed, the checkpoint read at a **pinned
  revision** (`5bc26a6fb0487f3f00a2a7313135103a005b1b67`) with
  `weights_only=True` and the four-entry allowlist of design decision 4, the
  `module.backbone.*` tensors loaded with **nothing missing and nothing
  unexpected**, and `module.last_layer_style` applied to the pooled output.
  Verify: a `models`-suite test (real checkpoint, never in CI) asserting width
  768, unit rows, a batch keeping its order, and the refusal when a tensor is
  missing; a unit test that the allowlist is exactly those four inert types and
  that `weights_only=False` appears nowhere in the repository.
- [ ] 2.3 The leaning of design decision 2: mean similarity of "same look,
  different picture" over mean similarity of "same picture, different look",
  per model, with the per-look breakdown beside it. Verify: unit tests of the
  arithmetic on hand-made vectors — a model that is perfectly style-leaning, one
  that is perfectly subject-leaning, and the degenerate corpus where one of the
  two sets is empty.
- [ ] 2.4 `scripts/style_benchmark.py` runs the candidate and `dinov2-large`
  over the built corpus and prints a Markdown table: the two averages, the
  leaning, the per-look rows, the corpus's size and looks, and the pinned
  revision. Verify: the command runs end to end against the demo pictures and
  prints the table; it writes nothing (the working tree is clean afterwards).

## 3. The decision

- [ ] 3.1 Run it over at least 100 photographs of the demo corpus and record
  the numbers. The bound is fixed in design decision 2: a key is earned only at
  **leaning ≥ 3 × the incumbent's**. Verify: the table is in
  `docs/how-to/benchmarks.md` under the exact command that produced it, with
  the corpus and the revision named.
- [ ] 3.2 `docs/adr/ADR-006-style-as-a-third-key.md`: the numbers, the corpus
  and its looks, the bound, and the decision — **including "no key" as a
  decision of the same standing** (design decision 5). It says in its own words
  that filters are not painters and what that limits the claim to. Verify: the
  ADR index carries its row; every number in it matches the how-to exactly.
- [ ] 3.3 Reconcile the plan with what was decided: `openspec/ROADMAP.md` and
  `docs/explanation/requirements.md` §9 — row 18 is this measurement, and
  shipping the key is row 18a, proposed only if ADR-006 says yes. Verify: both
  re-read whole; no document promises a third key as settled.

## 4. The rule this change followed

- [ ] 4.1 The `embedding-models` delta lands as written: a key earns its place
  by a published, re-runnable measurement with a bound fixed beforehand, and
  "not added" is an outcome of the same standing. Verify: `openspec validate
  --strict`; the ADR and the how-to are the evidence its scenarios describe.
- [ ] 4.2 `docs/how-to/benchmarks.md` gains the fourth section with the command
  in its exact form, what the two averages mean, and what the measurement does
  **not** say. Verify: re-read whole after the last edit; every command in it
  was run.

## 5. Closing the change

- [ ] 5.1 A demonstrated failing input for every new or changed check (high
  tier): each look's determinism, the two corpus bounds, the allowlist, the
  missing-tensor refusal, the width check, and the leaning's two degenerate
  cases. Verify: one table, one row per check, each a run with that one edit and
  the file restored afterwards.
- [ ] 5.2 `openspec validate stretch-style-search --strict` passes and every
  task above is checked with its evidence.
- [ ] 5.3 Run locally everything CI runs, in CI's own form:
  `FORCE_COLOR=1 CI=true make check`, `openspec validate --all --strict`,
  `sh -n scripts/*.sh`, every `scripts/*_test.sh`,
  `FORCE_COLOR=1 CI=true make test-integration` with the database up,
  `make audit`, and `make image` — the image especially, because this change
  adds a dependency and the point of the group is that the image does not grow.
  Verify: each command's result is recorded here, with the image's size beside
  the one before this change.
- [ ] 5.4 Hand over for the push: `handoff.md` at `awaiting-gate-2`, the
  mechanical floor passing, and the branch ready. Verify:
  `scripts/pregate-verify.sh gate2 stretch-style-search` prints all checks
  passed and its output is recorded in the handoff. The green CI run is the
  gate's prerequisite rather than this task's evidence, so the request waits for
  the user's push and their report of the run.
