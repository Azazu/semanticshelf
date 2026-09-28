# ADR-005: a query encoder answers in another model's space, and four languages are claimed

**Date:** 2026-09-28
**Status:** accepted
**Related:** ADR-001 (one space per model key, and vectors of different models never compared); FR-TXT-5 (the English-only boundary this lifts); authored by the OpenSpec change `stretch-multilingual-queries`

## Context

The service answered in English and said so. FR-TXT-5 made the limit a stated
boundary rather than a defect, the README named it among three, and §9 of the
specification allowed lifting it "only with numbers".

Two shapes were available, and the specification named both: a multilingual
CLIP **pair** as a new model key, or a multilingual **text tower aligned to the
image space this service already stores vectors in**. The second is cheaper by
an order of magnitude — no migration, no second index, no re-indexing of the
corpus — and it was verified before it was proposed:
`M-CLIP/XLM-Roberta-Large-Vit-L-14` is a text tower trained against OpenAI CLIP
ViT-L/14's images, which is the checkpoint behind this service's
`clip-vit-l14`.

It also collides, at first sight, with the oldest invariant here: the `model`
column is part of an embedding's identity, and vectors of different models are
never compared.

## Decision

**A query encoder is a participant of its own, declared beside the model
registry rather than inside it.** `QUERY_ENCODERS` maps an encoder key to the
storage key whose space it answers in. Nothing is ever written under an
encoder's key — no row, no CHECK, no index, no queued work — so enabling one
needs no migration and changes no stored vector.

The invariant is **narrowed rather than broken**: what may not be compared is
vectors that do not share a space. A model's own text side and an aligned
encoder both put a query into one space, and which of them did it is named in
every answer (`model` and `encoder`), because two scores are comparable only
within that pair.

**The key is bound to the assets the numbers were measured on.** Both
repositories are read at a pinned revision —
`40afa80a85e8efa990384a24bbe5a1f6f1cc81b5` for the checkpoint, its config and
the tokenizer, `c23d21b0620b635a76227c604d44e43a9f0ee389` for the
`xlm-roberta-large` config the architecture is built from — and, unlike the two
storage models, **there is no setting to point the key elsewhere**. A model's
checkpoint may be substituted because a mirror or a compatible fine-tune is an
operator's choice and the width check is the guard; an encoder's key claims
alignment with another model's space, which nothing at runtime can verify and
which the measurement below backs for particular bytes. Other weights are
another encoder, with a key and numbers of their own. (Gate 2 round 2 asked for
exactly this: a substitution that kept the key would have carried these
published numbers along with it.)

**A checkpoint that does not fill the architecture is refused at load.** The
transformer is built from a config and the weights are poured in with
`strict=False`, which is what lets through the one buffer transformers 4.x
persisted and 5.x derives; what that call *reports* is then checked. A missing
tensor would otherwise stay randomly initialised, pass the width probe, and
rank under a key whose numbers are published.

**The adapter is written here rather than imported.** The package the model
card recommends (`multilingual-clip` 1.0.10, June 2022, MIT) does not load
under this project's transformers 5.17 — it fails with a meta-device error from
`from_pretrained` — and the model it wraps is a transformer, a mean pool over
the attention mask and one linear layer, all of which are in the checkpoint.
The checkpoint is read with `weights_only=True`: it is a pickle, and the
repository's safetensors copy exists only in an unmerged pull request.

**Four languages are claimed: Russian, German, French and Spanish.** The other
44 the encoder accepts are untested and are described that way.

## The measurement

`scripts/multilingual_benchmark.py`, published in
[`docs/how-to/benchmarks.md`](../how-to/benchmarks.md): 500 assets of the demo
corpus with a `clip-vit-l14` vector, 21 concepts (a COCO tag carried by 3 to 10
assets, at least 20 of them, printed with their phrase in every language),
ranked exactly rather than through the index. A language is claimed only when
it clears **both** bounds — mean recall@10 of at least 0.5, and at least 0.8 ×
the English baseline's over the same concepts.

| language | asked by | mean recall@10 | worst concept | mean agreement@10 | claimed |
|---|---|---|---|---|---|
| en | `clip-vit-l14` | 0.649 | apple 0.000 | 1.000 | baseline |
| en | `mclip-xlmr-l14` | 0.683 | apple 0.000 | 0.857 | yes |
| ru | `mclip-xlmr-l14` | 0.684 | apple 0.000 | 0.843 | yes |
| de | `mclip-xlmr-l14` | 0.665 | apple 0.000 | 0.843 | yes |
| fr | `mclip-xlmr-l14` | 0.683 | apple 0.000 | 0.871 | yes |
| es | `mclip-xlmr-l14` | 0.659 | apple 0.000 | 0.857 | yes |

Two conditions rather than one, because either alone can be cleared by an
answer nobody would want: against a baseline of zero the relative bound passes
an encoder that finds nothing, and the absolute bound alone cannot say whether
the encoder or the corpus is the limit.

## Consequences

- **A query in the four named languages is answered from the vectors already
  stored.** Nothing was re-indexed and no schema moved.
- **The encoder is off by default.** `ENABLED_QUERY_ENCODERS` is empty, and a
  build that does not name it downloads nothing; a build that names it without
  enabling `clip-vit-l14` refuses to start, because its vectors would have
  nothing to be compared with.
- **`min_score` does not carry across the pair.** A threshold tuned for CLIP's
  English tower means something else for the encoder, and the API says so where
  the parameter is documented.
- **The English row is the finding worth remembering.** Asked in English, the
  encoder differs from the baseline by about as much as the other languages do
  (agreement 0.857) and scores slightly higher. The difference between pages is
  a different tower, not the cost of a translation.
- **What is not decided here.** Whether a multilingual *pair* would do better
  is unmeasured: it would need its own key, its own index and a re-index of the
  corpus, and this change bought the answer without them. If the encoder's
  repository ever disappears, the service runs exactly as before — which is
  another consequence of it owning no stored data.

## Alternatives considered

**A multilingual CLIP pair as a new model key** — the shape the specification
names first. It obeys the identity rule without any narrowing, and it costs a
migration, a partial index, a full re-index of the corpus and a weaker image
tower than ViT-L/14. Rejected for this change, and still available: a new key
is what this project does when a space really is new.

**Translating the query into English before embedding it.** Rejected outright:
it makes a translation service part of the search path, and the mistakes it
makes would be invisible in the ranking.
