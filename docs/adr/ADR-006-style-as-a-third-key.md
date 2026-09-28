# ADR-006: a model key earns its place by measurement, and this is the style candidate's

**Date:** 2026-09-28
**Status:** proposed
**Related:** ADR-001 (one space per model key; vectors of different models never compared); ADR-002 (an index family decided by measurement, and the precedent for deciding to change nothing); `embedding-models` — "A model key earns its place by measurement"; authored by the OpenSpec change `stretch-style-search`

> **This record is incomplete.** The numbers, the decision it reads off them,
> and the status above land when the published command has been run over the
> corpus it names. Everything below this line was fixed **before** the run, so
> that the bound could not be fitted to the table.

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

*Pending the run: the numbers, and what they decided.*

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

*Pending the decision above.*

## Supersedes

No ADR clause. ADR-001's rule that a key is an identity is what makes this
record necessary, and is unchanged by it.
