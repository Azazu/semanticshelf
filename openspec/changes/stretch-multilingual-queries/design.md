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
| Empty, zero and null inputs | An empty query is already refused by the text-search bound (FR-TXT-2); the encoder is never reached. A query of only whitespace, or of a script the tokenizer has no tokens for, produces a vector like any other — what must not happen is a **zero vector**, which cannot be normalised, so the adapter uses the same `ZeroVectorError` guard as every other embedder. A query longer than the encoder's context is **cut, and says so**: `EmbeddingResult.truncated` is what the API answers as `query_truncated`, and an encoder that cut a query silently would answer a question the client did not ask (`embedding-models`, "Text longer than the model's context is truncated and the caller is told"). |
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

Thirty lines — tokenize with truncation at the model's context and report what
was cut, run XLM-R, mean-pool over the attention mask, apply the linear head,
normalise — against a dependency whose last release predates the pinned
transformers by three majors and fails on it (Context). The project's
anti-overengineering rule asks what an existing tool cannot cover; here the
tool does not run at all.

The checkpoint is read at a **pinned revision** —
`40afa80a85e8efa990384a24bbe5a1f6f1cc81b5`, what `main` pointed at when this was
measured (the repository has not moved since 2022-09-15, which is a fact about
today rather than a guarantee about tomorrow) — with
`torch.load(..., weights_only=True)`: no pickle is executed, and the
safetensors copy that exists only in an unmerged pull request is not used. The
revision pins all three files the adapter reads from that repository — the
config, the checkpoint and the tokenizer — because a tokenizer that changes
answers differently with the same weights.

The transformer is built with `AutoModel.from_config` from the config of
`FacebookAI/xlm-roberta-large` (a few kilobytes from the Hub, cached like
everything else) rather than by downloading that model's own 2.2 GB of weights,
which the checkpoint already contains — and **that fetch is pinned too**, to
`c23d21b0620b635a76227c604d44e43a9f0ee389`, because a config that changes
builds a different model under the same encoder key. Two repositories, two
revisions, and the encoder is the pair:

| What | Repository | Revision |
|---|---|---|
| checkpoint, its config, tokenizer | `M-CLIP/XLM-Roberta-Large-Vit-L-14` | `40afa80a85e8efa990384a24bbe5a1f6f1cc81b5` |
| the architecture the weights are poured into | `FacebookAI/xlm-roberta-large` | `c23d21b0620b635a76227c604d44e43a9f0ee389` |

Both are printed by the benchmark, recorded in ADR-005 and named in the models
how-to. A deployment therefore loads the encoder the numbers were taken from,
and moving either revision is an edit to a constant, a new measurement and a
new line in the ADR.

*What this guarantees:* no new dependency, a load that executes no code from
the checkpoint, and that the bytes loaded are the bytes measured — the revision
is in the code, in the benchmark's output and in the ADR. *What it does not:*
it does not make the model ours — the weights and their behaviour are still
someone else's, and the docs say so with the licence question stated as open
(decision 5); and a pin cannot outlive the repository being taken down, which
is why the encoder is optional and the service runs without it.

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

- **recall@10 by tag** — the query names a concept (`zebra`, `traffic light`,
  `tennis racket`, …) in a language; a result is right when the asset carries
  the matching tag, and the number is *how many of the pictures that carry it
  reached the first ten*. Recall rather than precision, because precision@10 is
  capped at `relevant/10` for a concept the corpus holds four pictures of — a
  perfect answer would score 0.4 and look like a failure.
- **agreement@10 with English** — the same concept in English and in the
  language, as sets of asset ids: how much of the English page the translated
  query reproduces. This is the number that says "the same answers", which is
  what a reader actually wants to know.

Every concept is reported with **how many assets carry its tag**, so a reader
can see what each number was computed against.

Both are reported per language for Russian, German, French and Spanish, over
the concept set the rules below select — at least 20 of them, and the run prints
how many survived — with the English CLIP text side as the baseline row.

**The bound is two conditions, fixed here rather than after the data is seen,
and neither can be passed by an encoder that answers badly.**

1. *Absolute:* mean recall@10 over the concept set is at least **0.5** — half
   of what the corpus holds for a concept reaches the first ten.
2. *Relative:* mean recall@10 is at least **0.8 ×** the English baseline's over
   the same concepts — "it works the way English does, allowing for what
   translation costs".

The relative condition alone would be a trap: against a baseline of zero, an
encoder that finds nothing passes. The absolute condition alone would not say
whether the encoder or the corpus is the limit. Both, and a language clears the
bound only by clearing both.

**The concept set is chosen so that the numbers can mean something**, by rules
that do not look at any language's results:

- a concept enters only when the corpus carries its tag on **at least 3 and at
  most 10** assets — fewer and one picture decides the score, more and recall@10
  cannot reach 1 however good the answer is;
- the **English baseline must itself clear 0.5** on the set. If it does not, the
  measurement says so and reports nothing about any other language: a concept
  set the service's own model cannot answer measures the corpus, not the
  encoder;
- at least **20 concepts** must survive these rules, or the run reports that the
  corpus is too small for the question rather than publishing a number.

Agreement@10 is **published without a bound**. It is the number that answers
"does it return the same pictures", and no threshold on it would mean anything
before the first measurement — a low agreement with a high recall is a
different answer of the same quality, not a failure. A language that misses the
bound is published with its numbers and named as not supported, rather than
dropped from the table.

The bounds are on the mean over the concept set, not on any single concept, for
the same reason change 14's recall bound is on the mean: one concept the corpus
barely holds would otherwise decide the question. The worst concept per language
is published beside the mean, and is not bounded.

*What this guarantees:* the claim "these four languages work" has a command
behind it that anyone can re-run, against a concept set whose composition the
same command prints, at the two revisions it names. *What it does not:* it says
nothing about the other 44 languages the encoder accepts (the docs name them as
unmeasured), nothing about queries longer or vaguer than a concept name, and
nothing about a corpus other than the demo one — a claim about somebody's own
pictures needs their own run.

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
