# Proposal — stretch-style-search

**Risk-Tier:** high

Three triggers, any one of which would be enough: the change **adds a
dependency** (`open_clip_torch`, which pulls `torchvision` and `timm`), it
**downloads a model** — egress from a process this repository ships — and the
decision it produces governs whether a later change writes a migration that
adds a CHECK value and an index. Gate 1 before implementation, a demonstrated
failing input for every new check.

## Why

The roadmap's row 18 says "a style embedding model as a third key with its own
index". Before this project writes that migration it owes an answer to a
question it has never had to ask: **what does a third key answer that the two
it already runs do not?**

That question is not rhetorical. `dinov2-large` already ranks pictures by
appearance, and appearance and style are neighbours. A style key costs a
migration, a partial index, a vector per asset for the whole corpus and
gigabytes of weights — and if what it returns is what DINOv2 returns, it is an
expensive synonym.

A probe run before this proposal says the question has an interesting answer.
Four photographs under six deterministic looks (grey, posterised, edges,
painterly, sepia and the original), with two numbers per model: how similar two
*different* photographs under the *same* look are, and how similar one
photograph under two *different* looks is.

| model | same look, different picture | same picture, different look | leaning |
|---|---|---|---|
| CSD ViT-L (candidate) | 0.507 | 0.551 | **0.92** |
| `dinov2-large` (already here) | 0.104 | 0.718 | 0.145 |

DINOv2 is a picture model: a picture stays itself whatever is done to its
colours. The style descriptor is nearly indifferent between the two — which is
what "ranks by style rather than by subject" looks like as a number. Four
pictures are an existence proof, not a measurement.

## What Changes

**This change measures and decides. It does not add the key.** That is a
deliberate reshaping of the roadmap's row, and the reason is the row's own
words: a third key is worth a migration only if it answers something. So:

- `scripts/style_benchmark.py` — builds a **style corpus** from the demo
  pictures by applying deterministic looks (no new download, no licence
  question: the pictures are the ones already there and the looks are code),
  then reports, per model, how much it leans toward style and how much toward
  subject, over the whole corpus rather than four pictures.
- The candidate is CSD ViT-L (`tomg-group-umd/CSD-ViT-L`, CC-BY-4.0), measured
  beside `dinov2-large`, which is the incumbent and the thing to beat.
- **ADR-006** records what the numbers decided: whether a style key is worth a
  third of every asset's storage and a third job per upload, and if so, which
  checkpoint and at what width.
- A requirement in `embedding-models`: **a key earns its place by
  measurement**, published and reproducible, before it is added. That is the
  rule this change follows and the one a later change will be held to.
- `openspec/ROADMAP.md` and the requirements register carry the reshaping: row
  18 becomes the measurement, and shipping the key — migration, index,
  re-index, `model=` on the picture searches — is row 18a, to be proposed only
  if ADR-006 says yes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `embedding-models`: a new model key is justified before it exists — the
  repository publishes what it answers that the existing keys do not, by a
  command anyone can re-run, and a candidate that does not clear the bound is
  not added.

## Impact

- **New:** `scripts/style_benchmark.py`, `docs/adr/ADR-006-*.md`, a section in
  `docs/how-to/benchmarks.md`, unit tests for the metric and the corpus rules,
  and a `models`-suite test of the candidate adapter used by the benchmark.
- **Changed:** `openspec/ROADMAP.md`, `docs/explanation/requirements.md` (§9 and
  §7's row), `pyproject.toml` and `uv.lock` (the new dependency group).
- **Unchanged:** the service. No endpoint, no schema, no migration, no stored
  vector, no setting the API reads — the candidate is loaded by a benchmark,
  not by `create_app`. `EMBEDDING_MODELS`, the CHECK and the indexes stay as
  they are.
- **Dependencies:** `open_clip_torch` (MIT, 2.32.0, April 2025), and with it
  `torchvision` and `timm`. Justified rather than assumed: the checkpoint is in
  OpenAI-CLIP's own module layout (`backbone.transformer.resblocks…`), which
  `transformers` cannot build; open_clip builds exactly that tower and the
  probe loaded the weights into it with **0 missing and 0 unexpected** tensors.
  Writing that mapping by hand — splitting `in_proj_weight` into q, k and v and
  renaming every block — is the alternative, and it is more code to own than a
  maintained package. The dependency goes in a **group of its own**, so the
  service image does not carry it.
- **Disk:** about 1.7 GB in the model cache for the candidate, on a machine
  that runs the benchmark. A deployment downloads nothing.

## Non-goals

- **No third key in this change.** No migration, no CHECK value, no index, no
  re-index, no `model=` on the picture searches. If ADR-006 says yes, that is
  row 18a with its own gates.
- **No art corpus.** WikiArt's licence is `unknown` ("Data files © Original
  Authors"), which collides with the rule change 9 set for this project: only
  licences that permit reuse, because a thumbnail is a derivative work. A
  museum's CC0 API would be a demo-dataset change of its own.
- **No claim about artistic style.** The looks are filters, not painters. What
  is measured is whether a model separates *how a picture looks* from *what is
  in it*, which is the property a style key would be bought for; a claim about
  Impressionism needs Impressionists.
- **No second style candidate.** One candidate against the incumbent. A
  comparison of style models is a different question and a longer change.
- **No UI work.**
