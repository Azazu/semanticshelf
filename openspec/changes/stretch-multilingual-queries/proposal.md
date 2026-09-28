# Proposal — stretch-multilingual-queries

**Risk-Tier:** high

Two triggers from this project's own table, and either one is enough. The
change **downloads a model** — 2.24 GB from the Hugging Face Hub on first use,
which is egress from a process this repository ships. And it **widens what the
search endpoint accepts**, by letting a query be embedded with a checkpoint
other than the one whose vectors are being ranked: the rule that vectors of
different models are never compared is the oldest invariant here, and this
change narrows it rather than breaking it. Gate 1 before implementation, a
demonstrated failing input for every new check.

## Why

The service answers in English and says so — FR-TXT-5 makes the limit a stated
boundary, the README names it among the three, and `docs/how-to/searching.md`
tells a reader that other languages degrade toward a random ranking. §9 of the
specification allows lifting it "only with numbers".

The numbers are now cheap to get, because of a fact this change was probed
for before it was proposed: a multilingual text tower exists that was trained
to land in the image space of the very checkpoint this service already stores
vectors from — OpenAI CLIP ViT-L/14. A query in Russian can therefore be
answered **by the vectors already in the database**. Nothing is re-indexed,
no migration runs, no second copy of the corpus appears.

The probe (recorded in `design.md`) ran four concepts in English and Russian
against 24 pictures of the demo corpus embedded by the service's own image
tower. The Russian query returned the same top-3 as the English one in three
cases out of four, in the same order, at almost the same scores; the fourth
differed in third place only. That is what makes this worth building — and
what has to be measured properly rather than asserted from four queries.

## What Changes

- A **query encoder**: a new kind of participant, next to the embedding models
  that own stored vectors. It embeds a query into the space of a storage model
  it names, and owns no column, no index and no row. `mclip-xlmr-l14`
  (`M-CLIP/XLM-Roberta-Large-Vit-L-14`) is the first, and it answers in
  `clip-vit-l14`'s space.
- `GET /api/v1/search/text` accepts a query encoder in `model=`. The answer
  names both: the storage model whose vectors were ranked, and the encoder that
  embedded the query, because a score is comparable only within that pair.
- `app/ml/mclip.py` — the adapter, text only. No new dependency: the package
  the model card names (`multilingual-clip` 1.0.10, June 2022) does not load
  under the transformers this project pins, and the model it wraps is a
  transformer plus one linear layer, both of which are in the checkpoint.
- A **measurement**, because the boundary is lifted only with numbers:
  `scripts/multilingual_benchmark.py` reports, per language, how often a query
  finds pictures that carry the matching corpus tag (precision@k) and how much
  its page agrees with the same query in English (agreement@k). Russian,
  German, French and Spanish are measured and named; the encoder's other 44
  languages are stated as unmeasured.
- **ADR-005** records what the numbers decided, and `docs/how-to/benchmarks.md`
  grows the third section that produces them.
- The English-only limit is **amended, not deleted**: FR-TXT-5, the README's
  boundary and `docs/how-to/searching.md` say which languages were measured,
  with what result, and that a picture query has no language at all.

## Capabilities

### New Capabilities

None. A query encoder is a new mechanism, not a new capability: what it serves
is text search, which already has a spec.

### Modified Capabilities

- `text-search`: the requirement that a query is embedded with "that model's
  text side" widens to a named encoder that declares the space it answers in,
  with the no-comparison-across-spaces rule restated in terms of that space and
  the alignment held to published numbers.
- `embedding-models`: the model registry gains the query-encoder table beside
  it — what an encoder declares, what a build may enable, and the refusal when
  one is asked for that this build does not run.

## Impact

- **New:** `app/ml/mclip.py`, `scripts/multilingual_benchmark.py`,
  `docs/adr/ADR-005-*.md`, tests for the adapter (against the real checkpoint,
  in the `models` suite that CI never runs) and for the routing and refusals
  (against the fake).
- **Changed:** `app/domain.py` (the query-encoder table and its modality),
  `app/ml/registry.py`, `app/core/settings.py` (which encoders a build enables),
  `app/api/search.py` and `app/schemas/search.py` (the answer names the pair),
  `app/services/search.py`, `docs/how-to/searching.md`,
  `docs/how-to/benchmarks.md`, `docs/reference/settings.md`, `README.md`,
  `docs/explanation/requirements.md` (FR-TXT-5).
- **Unchanged:** the database. No migration, no CHECK, no index, no re-indexing
  — the vectors being ranked are the ones already stored under `clip-vit-l14`.
  `POST /search/image` and `GET /assets/{id}/similar` are untouched: a picture
  has no language.
- **Dependencies:** none added. The adapter uses `transformers`, `torch` and
  `huggingface_hub`, all already pinned. This is deliberate and was checked:
  the package the model card recommends is four years unmaintained and fails on
  the pinned transformers, and copying thirty lines of model glue under our own
  tests is the smaller liability.
- **Disk:** 2.24 GB in the model cache, alongside the 3.4 GB of CLIP and the
  2.4 GB of DINOv2.

## Non-goals

- **No translation.** The service does not translate a query into English and
  search with that; the encoder embeds the words it was given.
- **No language detection**, and no `lang=` parameter. The encoder is
  multilingual; asking for it is asking for it.
- **No new storage key and no re-indexing.** Nothing is written to
  `embeddings`, so the dimension CHECK, the per-model index and the queue are
  untouched.
- **No multilingual image side.** `POST /search/image` and `/similar` keep
  ranking DINOv2 vectors; a picture is not in a language.
- **No claim beyond what is measured.** Four languages are measured and named;
  the rest are reported as untested rather than implied.
- **No UI work.** The Streamlit pages keep their English placeholder text; the
  encoder is reachable through `model=` like any other.
