# Design — stretch-multilingual-queries

## Context

See `proposal.md` — Why. What shapes the approach, all of it verified before
this document was written:

- **The model.** `M-CLIP/XLM-Roberta-Large-Vit-L-14` is a text tower trained to
  land in the image space of OpenAI CLIP ViT-L/14 — the checkpoint behind this
  service's `clip-vit-l14`, whose vectors are already in the database. Its
  `config.json` says `modelBase: xlm-roberta-large`, `numDims: 768`,
  `transformers_version: 4.8.1`; the checkpoint carries the transformer's
  weights **and** the projection (`LinearTransformation.weight` of shape
  (768, 1024), plus its bias).
- **The package the model card recommends does not work here.**
  `multilingual-clip` 1.0.10 (PyPI, 2022-06-02, MIT, its last release) fails
  on this project's transformers 5.17 with `RuntimeError: You are using
  from_pretrained with a meta device context manager` — its `from_pretrained`
  calls `AutoModel.from_pretrained` inside a context transformers 5 now
  initialises under a meta device.
- **The model is small enough to state in full**: XLM-RoBERTa large, mean
  pooling over the attention mask, one linear layer. A probe built exactly that
  from the checkpoint (`torch.load(..., weights_only=True)` of the main
  revision's `pytorch_model.bin`, `AutoModel.from_config` for the transformer,
  `torch.nn.Linear` for the head) and loaded it with **0 missing and 1
  unexpected** tensor, producing vectors of width 768.
- **It answers.** Against 24 pictures of the demo corpus embedded by the
  service's own image tower:

  | Query | `clip-vit-l14`, English | the encoder, Russian |
  |---|---|---|
  | a zebra in the grass / зебра в траве | 110211, 119445, 104619 | 110211, 104619, 119445 |
  | people playing tennis / люди играют в теннис | 012120, 001000, 119995 | 012120, 001000, 119995 |
  | a red traffic light… / красный светофор… | 015272, 122046, 111179 | 015272, 122046, 015517 |
  | an elephant / слон | 021903, 107851, 110211 | 021903, 107851, 110211 |

  Four queries are an existence proof, not a measurement. The measurement is
  decision 4.
- **Where the weights come from matters.** The main revision carries only
  `pytorch_model.bin`; the `model.safetensors` that appeared in the local cache
  came from `refs/pr/2`, an **unmerged pull request** of the model repository.
  The model card declares **no licence**, and the Hub API returns none; the
  project behind it (FreddeFrallan/Multilingual-CLIP) is MIT.
- **The invariant this change touches** is the oldest one here: "the `model`
  column is part of an embedding's identity and vectors of different models are
  never compared" (§1 of the specification, `embedding-storage`, ADR-001).

## Goals / Non-Goals

**Goals**

- A query in Russian, German, French or Spanish answered from the vectors
  already stored, with the same honesty about scores the service has for
  English.
- The identity rule narrowed precisely rather than loosened: what may not be
  compared is vectors of different **spaces**, and an encoder that claims a
  space is held to numbers.
- One authority for what a build runs: the model registry says what is stored,
  a table beside it says what may embed a query into which space.

**Non-Goals** (beyond the proposal's)

- No abstraction over "any encoder for any model". One encoder, one space, a
  table that a second entry can join later.
- No re-measurement of CLIP itself. The English numbers of change 14 stand;
  this measures what a translated query costs relative to them.

## Applicability (high tier)

| Question | This change |
|---|---|
| Empty, zero and null inputs | An empty query is already refused by the text-search bound (FR-TXT-2); the encoder is never reached. A query of only whitespace, or of a script the tokenizer has no tokens for, produces a vector like any other — what must not happen is a **zero vector**, which cannot be normalised, so the adapter uses the same `ZeroVectorError` guard as every other embedder. |
| Crash around an external effect | The only external effect is the download on first load. A partial download is the Hub cache's problem and is retried by it; a load that fails leaves the registry without the encoder, so the next request tries again rather than serving a half-built model. Nothing is written to the database at any point. |
| Idempotent retries | The encoder is a pure function of its input: the same query gives the same vector, and a repeated search repeats the ranking. There is no state to make idempotent. |
| Authorization boundary | n/a — the service has no authentication, and this adds no privileged path. |
| Concurrent writers | n/a — nothing is written. The registry's per-process cache is the same one every model already uses. |
| Money and rounding | n/a. |
| Deletion and expiry | n/a — no row, no lease, no file. |

## Decisions

### 1. A query encoder is a table beside the model registry, not a model key

`EMBEDDING_MODELS` is the authority on what may be **stored**: every key in it
has a width, a CHECK constraint carrying that width, and a partial index. The
encoder stores nothing, so putting it there would be a lie that the migration
would then have to carry forever.

Instead `app/domain.py` gains `QUERY_ENCODERS: Mapping[str, str]` — encoder key
→ the storage key whose space it answers in — with the same treatment the model
tables already get: a unit test holds it against the registry of adapters, and
another refuses an entry whose target is not a known storage key.

*What this guarantees:* a vector is compared only with vectors of the space it
was produced for, and the space is named in the table rather than inferred.
*What it does not:* it does not verify that the encoder really lands in that
space — no code can, since that is a property of the training. Decision 4 is
how the claim is checked, and it is a measurement, not an assertion.

*Alternative considered:* a second model key with its own stored vectors (the
proposal's option B). Rejected for this change: it needs a migration, a new
index and a re-index of the corpus to buy the same answers, and its image tower
would be a different one from the service's.

### 2. The adapter is written here, not imported

Thirty lines — tokenize, run XLM-R, mean-pool over the attention mask, apply the
linear head, normalise — against a dependency whose last release predates the
pinned transformers by three majors and fails on it (Context). The project's
anti-overengineering rule asks what an existing tool cannot cover; here the
tool does not run at all.

The checkpoint is read from the **main** revision with
`torch.load(..., weights_only=True)`: no pickle is executed, and the
safetensors copy that exists only in an unmerged pull request is not used. The
transformer is built with `AutoModel.from_config` and the config of
`xlm-roberta-large` (a few kilobytes from the Hub, cached like everything else)
rather than by downloading that model's own 2.2 GB of weights, which the
checkpoint already contains.

*What this guarantees:* no new dependency, and a load that executes no code
from the checkpoint. *What it does not:* it does not make the model ours — the
weights and their behaviour are still someone else's, and the docs say so with
the licence question stated as open (decision 5).

*Alternative considered:* vendoring `multilingual-clip`'s module into the
repository. Rejected: the same thirty lines with someone else's structure and
a second set of names for the same concepts.

### 3. `model=` names either a storage model or an encoder; the answer names both

The parameter stays one parameter. The service resolves the name in two steps:
a storage key means "rank these vectors with this model's own text side" as
before; an encoder key means "embed with this, rank the vectors of the space it
declares". The response gains the encoder's name beside `model`, because a
score is comparable only within a (space, encoder) pair — two encoders in one
space do not produce the same numbers, and the answer must not let a reader
believe otherwise.

*What this guarantees:* a client can tell which pair produced a score.
*What it does not:* it does not make scores from different pairs comparable, and
the API says so in the same sentence as `min_score` — a threshold tuned for
English CLIP is not a threshold for the encoder.

*Alternative considered:* a separate `encoder=` parameter. Rejected: two
parameters that may disagree (`model=dinov2-large&encoder=mclip-xlmr-l14`) is a
refusal to write and a refusal to explain; one name that resolves to a pair has
no such state.

### 4. The boundary is lifted by a measurement, with two metrics and no new labels

`scripts/multilingual_benchmark.py`, beside the two benchmarks change 14 left,
against the demo corpus (which carries COCO's own labels as tags):

- **precision@k by tag** — the query names a concept (`zebra`, `traffic light`,
  `tennis racket`, …) in a language; a result is right when the asset carries
  the matching tag. Ground truth is the corpus, not an opinion.
- **agreement@k with English** — the same concept in English and in the
  language, as sets of asset ids: how much of the English page the translated
  query reproduces. This is the number that says "the same answers", which is
  what a reader actually wants to know.

Both are reported per language for Russian, German, French and Spanish, over at
least 30 concepts, with the English CLIP text side as the baseline row.

**The bound is relative, and fixed here rather than after the data is seen.** A
language is claimed only when its mean precision@10 is at least **0.8 × the
English baseline's** mean precision@10 over the same concepts — "it works the
way English does, allowing for what translation costs". The bound is on the
mean over the concept set, not on any single concept, for the same reason
change 14's recall bound is on the mean: one concept the corpus barely holds
would otherwise decide the question.

Agreement@10 is **published without a bound**. It is the number that answers
"does it return the same pictures", and no threshold on it would mean anything
before the first measurement — a low agreement with a high precision is a
different answer of the same quality, not a failure. A language that misses the
precision bound is published with its number and named as not supported, rather
than dropped from the table.

*What this guarantees:* the claim "these four languages work" has a command
behind it that anyone can re-run. *What it does not:* it says nothing about the
other 44 languages the encoder accepts, and the docs name them as unmeasured.

*Alternative considered:* hand-labelled relevance for a set of queries.
Rejected for this change: it cannot be re-run by a command, and the corpus
already carries a ground truth that costs nothing.

### 5. What the docs must say, and where each thing is said once

- `docs/how-to/searching.md` — the operational half: how to ask for the
  encoder, what the answer names, that a threshold does not carry across pairs,
  and which languages are measured.
- `docs/how-to/benchmarks.md` — the third section: the command, its output, and
  how to read it.
- **ADR-005** — why a query encoder rather than a model key, and what the
  numbers decided.
- `docs/explanation/requirements.md` — FR-TXT-5 amended in place: the
  English-only limit becomes "English, plus the languages §9's stretch measured
  and published", with the change and the ADR named.
- `README.md` — the boundary paragraph reworded to the measured claim, in one
  or two sentences, linking rather than restating.
- The **licence question** is recorded where the other licence facts live
  (`docs/reference/demo-dataset.md` is about the corpus, so this goes to the
  models how-to): the model card declares no licence, the upstream project is
  MIT, and a reader who needs certainty is told to ask the model's authors.

## Risks / Trade-offs

- **The encoder's space claim is only as good as the measurement** → two
  metrics, four languages, a published command, and numbers in an ADR rather
  than an assertion in prose.
- **A 2022 checkpoint with no declared licence** → the fact is recorded rather
  than smoothed over, the download is opt-in through configuration (a build
  that does not enable the encoder fetches nothing), and nothing in the service
  depends on it being there.
- **transformers may change again under the hand-written adapter** → it uses
  three public entry points (`AutoConfig`, `AutoModel.from_config`,
  `AutoTokenizer`) and one tensor layout, all of which are covered by a test
  against the real checkpoint in the `models` suite; CI never runs it, and the
  failure would be a local `make test-models` rather than a silent wrong answer.
- **2.24 GB more in the model cache** → the same volume the other two models
  live in, named in the docs, and only fetched when the encoder is enabled.
- **A reader may read "multilingual" as "as good as English"** → the published
  agreement@k is exactly the number that answers that, and the docs quote it
  beside the claim.

## Migration Plan

Nothing to migrate: no schema, no stored vector, no index. A build that enables
the encoder downloads it on first use (or by `models warm`); a build that does
not is unchanged in every respect. Rollback is removing the key from
configuration.

## Open Questions

None that change the specs, the approach or the tasks. The concept set is drawn
from the corpus's own most frequent tags, which the benchmark prints with its
results, so the measurement names its own inputs.
