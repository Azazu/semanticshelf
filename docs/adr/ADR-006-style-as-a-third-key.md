# ADR-006: a model key earns its place by measurement, and this is the style candidate's

**Date:** 2026-09-29
**Status:** accepted
**Related:** ADR-001 (one space per model key; vectors of different models never compared); ADR-002 (an index family decided by measurement, and the precedent for deciding to change nothing); `embedding-models` — "A model key earns its place by measurement"; authored by the OpenSpec change `stretch-style-search`

## Context

The roadmap asked for a style embedding as a third model key, with its own
dimension, CHECK value and index, exposed through `model=` on the picture
searches. Before writing that migration this project owed an answer to a
question it had never had to ask: **what does a third key answer that the two it
already runs do not?**

The question is not rhetorical. `clip-vit-l14` and `dinov2-large` both store a
vector for every asset, and both rank pictures by something that neighbours
style. A third key costs a migration, a partial index, a vector per asset for
the whole corpus, a job per upload and gigabytes of weights. If what it returns
is what one of those two returns, it is an expensive synonym.

**The candidate.** `tomg-group-umd/CSD-ViT-L` — Contrastive Style Descriptors,
from *Measuring Style Similarity in Diffusion Models* (2024), initialised from
CLIP ViT-L/14's image encoder and trained on a style-labelled subset of LAION.
Licence cc-by-4.0, declared. Its `config.json` says only
`{"model_type": "custom"}` and its weights file is a *training* checkpoint in
OpenAI CLIP's own module layout, so `transformers` cannot build it: the tower
comes from `open_clip`, in a dependency group of its own that the service image
cannot carry, and the backbone loads with nothing missing and nothing left over
once CLIP's own projection is removed **before** the load.

**The corpus is built, not found.** A corpus of paintings would be the natural
thing to measure on, and this project cannot have one: WikiArt's licence is
`unknown`, and change 9 set the rule that only licences permitting reuse are
taken, because the service re-encodes a thumbnail and that is a derivative work.
So the command applies six deterministic looks — the picture untouched,
grayscale, posterised, edges, painterly, sepia — to every photograph of a
folder. Two images share a look because the same function produced them and
share a subject because they came from the same photograph, which is a ground
truth nobody has to label and a re-run rebuilds exactly.

**The looks are filters, not painters.** What this corpus can support is a
statement about separating *how a picture looks* from *what is in it*, which is
the property a style key would be bought for. It is not evidence about
Impressionism. A claim about Impressionists needs Impressionists, and this
record makes none.

**The statistic was itself a decision.** The obvious number — mean "same look,
different picture" over mean "same picture, different look" — is moved by a
model's own similarity scale, and on the probe that preceded this change it
ranked `clip-vit-l14` as two thirds of the way to the candidate while CLIP put
the look first in nineteen triples out of a thousand. A ratio compares two
population means; a search compares two candidates against the same anchor. So
the deciding number is a **rank preference** — the fraction of triples (anchor,
a different photograph under the anchor's look, the anchor's photograph under
another look) where the look-mate outscores the picture-mate, a tie counting a
half. It is a proportion of a set the corpus fixes the size of, so it has no
zero denominator, no negative value and no dependence on that scale.

**The bound, fixed here and before the run.** A candidate earns a key when its
preference is strictly greater than `incumbent + (1 - incumbent) / 2`, against
the highest preference among the keys the service already stores. Half the
remaining distance to a perfect score is the only scale-free way to say
"decisively better" about a proportion: a multiplicative rule is meaningless
where `3 x 0.4` exceeds 1, and a fixed additive margin is easy against a weak
incumbent and unreachable against a strong one. It is one condition, not two:
the right-hand side is `(1 + incumbent) / 2`, so a candidate that clears it has
already been shown to prefer the look rather than the subject.

**"No key" is a decision of the same standing as "a key".** ADR-002 is the
precedent: it measured two index families, decided to change nothing, and that
record is one of the more useful things in this repository. What the
`embedding-models` requirement forbids is not a key that fails a bound — it is a
key whose value nobody measured.

## Decision

**No third key.** The candidate does not clear the bound, so `EMBEDDING_MODELS`,
the CHECK and the indexes stay as they are, and roadmap row 18a — the migration,
the index, the re-index and `model=` on the picture searches — is not proposed.

The run: 100 photographs of the demo corpus under six looks, 600 images, none
refused as one colour, 297 000 triples, corpus digest `7a0f6d0a346953a3`.
Candidate at `5bc26a6fb0487f3f00a2a7313135103a005b1b67`, tower
`ViT-L-14-quickgelu`. The incumbents are not pinned by this repository: the
model cache on the machine that produced these numbers held
`openai/clip-vit-large-patch14` at `32bd6428` and `facebook/dinov2-large` at
`47b73eef`, which is a diagnostic and not a statement about which weights
answered — each adapter resolves its weights and its processor separately,
without a revision. Pinning them is roadmap row 20.

```console
$ uv run --group style python scripts/style_benchmark.py --pictures 100
```

| model | prefers the look | same look, diff. picture | same picture, diff. look | ratio |
|---|---|---|---|---|
| `csd-vit-l` (candidate) | **0.282** | 0.407 | 0.562 | 0.724 |
| `clip-vit-l14` | 0.033 | 0.570 | 0.830 | 0.686 |
| `dinov2-large` | 0.012 | 0.055 | 0.739 | 0.074 |

The bound, fixed before the run, is `(1 + 0.033) / 2 = 0.516`. The candidate
reaches 0.282.

**What the numbers do say, and it is not nothing.** A style descriptor is not an
expensive synonym for what is already installed: on the question this corpus
asks, CSD separates *how a picture looks* from *what is in it* about **eight and
a half times** better than the best key the service stores. The worry that started this
change — that a third key would return what `dinov2-large` already returns — is
answered, and answered no.

**What they do not say is that it prefers the look.** 0.5 is indifference, and
0.282 is well below it: shown a photograph, the candidate still ranks the same
*subject* above the same *manner* more often than not. A key is bought to answer
"find me pictures that look like this one", and on this corpus none of the three
models answers that question — one of them is merely much closer than the others.

**A different bound would have decided differently, and here is which.** A
multiplicative rule — the shape this change first proposed, "at least three times
the incumbent" — sets the bar at `3 x 0.033 = 0.099` and admits the candidate
comfortably. It is published here because a reader is entitled to disagree with
the bound rather than with the arithmetic. The reason it was not used is that
eight times a number close to zero is still close to zero, and a proportion has
a meaning a ratio does not: the question is not "better than the incumbent" but
"does it prefer the look", and 0.282 does not.

**Most of the candidate's advantage comes from one filter, and that matters.**

| look | `csd-vit-l` | `clip-vit-l14` | `dinov2-large` |
|---|---|---|---|
| plain | 0.031 | 0.006 | 0.003 |
| grayscale | 0.046 | 0.003 | 0.002 |
| posterised | 0.087 | 0.004 | 0.002 |
| edges | **0.898** | 0.135 | 0.058 |
| painterly | 0.361 | 0.043 | 0.004 |
| sepia | 0.267 | 0.004 | 0.002 |

`edges` throws away colour and texture entirely, and on that the candidate is
nearly perfect. `plain` is the untouched photograph — the case a real style
search would actually run against — and there it scores 0.031, which is the same
order as the models it is supposed to beat. The average of 0.282 reads stronger
than what stands behind it, and a decision taken on the average alone would have
been taken on `edges`.

**The statistic was itself a finding.** The ratio of averages, which this change
proposed first and the Gate 1 reviewer sent back, is wrong on this table in both
directions. It puts `clip-vit-l14` at 0.686 against the candidate's 0.724 — five
per cent apart, "the same kind of model" — where the ranking says 0.033 against
0.282, a factor of eight and a half. And it puts `clip-vit-l14` at nine times
`dinov2-large` (0.686 against 0.074) where the ranking says 0.033 against
0.012, a factor of three. CLIP's similarities sit in a
narrow high band, which lifts both of its means together and tells a ratio
nothing about the order results come back in. Under the ratio *and* the original
3x rule the answer would also have been "no key" — but for a false reason, and a
different set of incumbents could as easily have flipped it to a false "yes".

**This table is the second one.** The first was measured against a tower built
with `nn.GELU`, where the checkpoint was trained under QuickGELU: CSD is
initialised from OpenAI's CLIP ViT-L/14, `open_clip`'s plain `ViT-L-14` config
sets `quick_gelu: false`, and an activation carries no tensors — so the weights
loaded with nothing missing and nothing unexpected while the network computed
something else. The Gate 2 reviewer found it. The wrong architecture **flattered
the candidate**: 0.395 rather than 0.282, and 0.981 rather than 0.898 on
`edges`. Both incumbent rows came back identical to the digit, which is what
established that the activation was the whole of the difference. The adapter now
asserts the built activation before it pours any weights in, because a tensor
report cannot see it.

## Alternatives considered

**A hand-picked set of public-domain artworks.** Rejected: not reproducible by a
command, and "hand-picked" is where a measurement starts to measure the person.

**A museum's CC0 API as a demo dataset.** A change of its own size, and one
about a corpus rather than about a key.

**Deciding on the ratio of averages.** Rejected on the evidence above: it is
confounded by how widely a model spreads its similarity scores, and the spec now
forbids reading a bound off a number a model's own scale can move. It is
published beside the preference as a diagnostic.

**Adding the key first and measuring afterwards.** The shape this change exists
to refuse. A key is permanent; a measurement is not.

**A second style candidate beside this one.** A different question — which style
model is better — and a longer change. This one asks whether the *category*
answers anything new.

## Consequences

**Nothing in the service changes.** No migration, no CHECK value, no index, no
re-index, no `model=` on the picture searches, no vector, no setting. The two
stored keys and their indexes are exactly what they were.

**The question is cheap to ask again.** `scripts/style_benchmark.py`, its corpus
builder and the `style` dependency group stay in the repository, and the command
is published in `docs/how-to/benchmarks.md`. A second candidate, or this one on a
corpus of real artworks, is one command rather than a change — which is the
difference between a decision that can be revisited and one that cannot.

**The rule outlives the candidate.** `embedding-models` now carries "a model key
earns its place by measurement": against every key of its kind, with a bound
fixed before the numbers are seen, read on a number a model's own similarity
scale cannot move. The next candidate is held to it, and this record is the
worked example of what clearing it would have looked like.

**What would change this answer.** A corpus of actual paintings rather than
filtered photographs — the looks here are filters, and the `plain` row is the
warning about how far they generalise. A candidate that prefers the look rather
than merely preferring it more than the incumbents do. Or a use for a style
vector that does not need it to win a ranking, which would be a different
question with a different bound.

**Accepted cost.** Three model passes over six hundred images — about seventeen
minutes on a laptop at four threads — to decide not to build something. That is
the cheap half of the trade: the migration, the index, the re-index of every
asset and a third job per upload are what was not spent.

**A defect found on the way.** The reviewer's objection to caching vectors
between runs could not be answered, because `clip-vit-l14` and `dinov2-large`
load a checkpoint *name* with no pinned revision and resolve their weights and
their processor separately — so a stored vector cannot be reproduced from its
model key alone. ADR-005 pinned the query encoder's revision for exactly this
reason; these two were never pinned. Recorded as roadmap row 20.

## Supersedes

No ADR clause. ADR-001's rule that a key is an identity is what makes this
record necessary, and is unchanged by it.
