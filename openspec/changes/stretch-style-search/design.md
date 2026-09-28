# Design — stretch-style-search

## Context

See `proposal.md` — Why. Everything below was established by a probe before
this document existed.

**The candidate.** `tomg-group-umd/CSD-ViT-L` — Contrastive Style Descriptors,
from *Measuring Style Similarity in Diffusion Models* (2024), initialised from
CLIP ViT-L/14's image encoder and trained on a style-labelled LAION subset.
Licence **cc-by-4.0**, declared (unlike change 17's encoder). Two files:
`pytorch_model.bin` and a `config.json` that says only
`{"model_type": "custom"}` — there is nothing for `transformers` to read.

**What the file actually is.** A *training* checkpoint, not a released model:
its top level is `model_state_dict`, `opt_bb`, `opt_proj`, `iter` (15000),
`args` and `fp16_scaler`. The weights are under `model_state_dict`, in OpenAI
CLIP's own module layout — `module.backbone.conv1`,
`module.backbone.transformer.resblocks.N.attn.in_proj_weight`, and so on — plus
two projections, `module.last_layer_style` and `module.last_layer_content`,
both **(1024, 768)**.

**Loading it is a security decision, not a detail.** `weights_only=True`
refuses the file: it carries pickled objects beside the tensors. The probe
established the exact, short list that unblocks it —
`numpy.core.multiarray.scalar` (which must be allowlisted under its *legacy*
module path, because numpy renamed the module to `numpy._core` while the
pickle still names the old one), `numpy.dtype`, `numpy.dtypes.Float64DType` and
`argparse.Namespace` — all of them inert data types that construct a value and
run nothing.

**The backbone loads cleanly, in one order only.** With `open_clip`'s
`ViT-L-14` visual tower and `visual.proj` removed **before** the load — CSD
replaces CLIP's own 1024→768 projection with its two (1024, 768) heads — the
checkpoint's `module.backbone.*` tensors load with **0 missing and 0
unexpected**. Removed after the load, the same call reports `proj` missing, so
"nothing missing" is a statement about a sequence, not about the weights alone.

**The probe's numbers**, four photographs × six looks, are in `proposal.md`.

## Goals / Non-Goals

**Goals**

- A number that says whether a style key answers something neither
  `clip-vit-l14` nor `dinov2-large` answers, produced by a command, over a
  corpus that command builds.
- A decision recorded where decisions live, including the decision *not* to add
  a key.
- The rule that produced it written into the specs, so the next candidate key
  is held to it rather than to an argument.

**Non-Goals** (beyond the proposal's)

- No abstraction over "any candidate model". One candidate, the keys the
  service already stores, one command.
- No attempt to make the benchmark reusable for text models.

## Applicability (high tier)

| Question | This change |
|---|---|
| Empty, zero and null inputs | A look that returns a **constant picture** — one colour everywhere, as a hard posterisation of a near-white photograph can — keeps no subject, so the pair it would form carries no ground truth. The corpus builder refuses that look for that picture (task 1.1) rather than measuring it, so nothing blank reaches an embedder and the zero vector the shared guard exists for cannot arise here. The deciding metric is a proportion of a finite set of triples: a corpus with fewer than two pictures or two looks yields no triple, and the benchmark refuses such a corpus rather than dividing by zero — the same refusal as its minimum size. The diagnostic ratio prints `undefined` rather than a value whenever its denominator is not positive. |
| Crash around an external effect | The only external effect is the checkpoint download; a failed one leaves nothing half-built, because the benchmark writes nothing anywhere. It reads no database at all — the corpus is files. |
| Idempotent retries | The looks are deterministic functions of the bytes, the vectors are deterministic given the weights, so a re-run reproduces the table exactly. That is the requirement's "can be re-run" scenario, not a nicety. |
| Authorization boundary | n/a — nothing in the service changes; the benchmark is a command an operator runs. |
| Concurrent writers | n/a — nothing is written. |
| Money and rounding | n/a. |
| Deletion and expiry | n/a. |

## Decisions

### 1. The corpus is made, not found

A style corpus of paintings would be the natural thing to measure on, and this
project cannot have one: WikiArt's licence is `unknown`, and change 9 set the
rule that only licences permitting reuse are taken, because the service
re-encodes a thumbnail and that is a derivative work. A museum's CC0 API would
be a demo-dataset change of its own size.

So the corpus is **built from the pictures already here**, by applying a fixed
set of deterministic looks — the picture untouched, grayscale, posterise,
edges, painterly, sepia — to each. Every look is a pure function of the bytes,
so the corpus is reproducible by the command, needs no download and raises no
licence question. The untouched picture is one of the looks and stays in: a
style search is run against ordinary photographs, and leaving them out would
measure a corpus nobody has.

*What this guarantees:* a ground truth nobody has to label — two pictures share
a look because the same function produced them, and share a subject because
they came from the same photograph. *What it does not:* these are filters, not
painters. The measurement is about separating *how a picture looks* from *what
is in it*, which is the property a style key is bought for; it is not evidence
about Impressionism, and the ADR will say so in those words.

*Alternative considered:* a hand-picked set of public-domain artworks. Rejected:
not reproducible by a command, and "hand-picked" is where a measurement starts
to measure the person.

### 2. Two ways to ask, and the one the decision rests on

For a corpus of `pictures × looks` the obvious statistic is two averages over
unit vectors — **same look, different picture** against **same picture,
different look** — and their ratio. The probe computed it, and it is the wrong
number for this question in two separate ways.

*It is undefined where it must not be.* Both averages are means of cosine
similarities, so either can be zero or negative even when neither set of pairs
is empty. A zero denominator has no value at all, a negative one reverses the
ordering, and a non-positive incumbent makes any multiplicative bound vacuous.

*It measures the wrong comparison.* A ratio compares two population means; a
search compares two candidates **against the same anchor**. `clip-vit-l14`
scores 0.675 on the ratio — far above `dinov2-large`'s 0.145, two thirds of the
candidate's — while ranking a shared look above a shared subject in 1.9% of
triples. Its similarities sit in a narrow high band, which lifts both means
together and says nothing about the order results come back in.

So the deciding number is a **rank preference**: over every triple (an anchor, a
different picture under the anchor's look, the anchor's picture under another
look), the fraction where the model scores the look-mate above the picture-mate,
a tie counting a half. It is a proportion of a set the corpus fixes the size of,
so it is never negative, never has a zero denominator, and is unchanged by any
monotone rescaling of a model's similarities — none of the three defects above
can arise in it. 0.5 is indifference; `dinov2-large` sits at 0.003.

**The bound, fixed here and before the full run.** One condition, against the
**best** of the keys the service already stores: the candidate closes more than
half the remaining distance to a perfect score,

```text
candidate > incumbent + (1 − incumbent) / 2
```

Its shape, not its value, is what was chosen: half the remaining headroom is the
only scale-free way to say "decisively better" about a proportion. A
multiplicative rule is meaningless where `3 × 0.4` exceeds 1; a fixed additive
margin is easy against a weak incumbent and unreachable against a strong one;
half the headroom costs the same effort wherever the incumbent stands.

It also subsumes the indifference floor, which is why there is no second
condition. The right-hand side is `(1 + incumbent) / 2`, and a preference lies
in [0, 1], so the bound is never below 0.5: a candidate that clears it has
already been shown to prefer the look rather than the subject. The comparison is
**strict** for the one point where that would otherwise be tight — a candidate at
exactly 0.5 against an incumbent at exactly 0 — and because a tie does not buy a
migration.

On the probe's four pictures the bound is 0.510 and the candidate reaches
0.450 — close enough that the full run genuinely decides, which is the shape a
measurement should have.

The ratio is published **beside** the preference, per model, as a diagnostic,
with `undefined` printed in place of a value whenever its denominator is not
positive. It decides nothing. The ADR records it, and records what it would have
decided, because "the obvious statistic was the wrong one here" is the most
transferable thing this measurement produced.

Both numbers are published per model, and the per-look breakdown with them, so a
reader can see which look carried each average.

*What this guarantees:* the decision is one comparison against every key the
service already runs, in a number that cannot be moved by how widely a model
spreads its similarities. *What it does not:* it says nothing about which model
retrieves *better* for a person's actual query — that would need human judgement
and a corpus this project cannot have.

### 3. The candidate's adapter lives in the benchmark, not in `app/`

Nothing in the service loads CSD in this change, so its loader belongs beside
the command that uses it (`scripts/`), not in `app/ml/`. If ADR-006 says yes,
the follow-up change moves it in, under the `Embedder` protocol, with the
`models`-suite test it will need then.

`open_clip_torch` is the dependency (proposal, Impact), in a **group of its
own**: the service image installs the runtime group and must not grow
`torchvision` and `timm` for a command it never runs.

*What this guarantees:* a measurement cannot change how the service behaves —
it cannot even be imported by it, which the layering test already enforces for
`scripts/`. *What it does not:* it does not spare the follow-up change from
writing the adapter properly; what moves is code that has already been run.

### 4. The checkpoint is read with a named allowlist, never with `weights_only=False`

Change 17 refused to execute a pickle and could, because its checkpoint was
plain tensors. This one is not: it is a training checkpoint with numpy scalars
and an `argparse.Namespace` in it. The two honest options are to allowlist
those four inert types, or not to use the model.

`weights_only=False` is the third option and is refused: it would let any
object in the file run code on load, which is the thing the flag exists to
stop. The allowlist is written out in the code with the reason beside it, and
each entry is a data type whose unpickling constructs a value — no callables,
no modules, nothing that can reach the filesystem.

*What this guarantees:* the load cannot execute code from the file. *What it
does not:* it does not make the weights trustworthy — nothing can; what it
bounds is the blast radius of reading them.

### 5. What the ADR must contain, whichever way it goes

The numbers **for the candidate and for every key the service already stores**,
the corpus it was run on with its size and its looks, the pinned revision, the
bound, the disagreement between the deciding metric and the diagnostic one, and
the decision — **including "no key" as a decision with the same standing as
"a key"**. Change 14 is the precedent: it measured, decided to change nothing,
and the record of that is one of the more useful things in this repository.

## Risks / Trade-offs

- **The filters are not styles** → stated in the ADR, in the how-to and in the
  spec's own wording ("how a picture looks"), and the corpus is printed with
  its looks so a reader sees exactly what was measured.
- **A new dependency for one command** → its own group, out of the image, MIT,
  maintained (3.3.0, February 2026), and justified against the hand-written
  alternative in the proposal.
- **A training checkpoint with pickled objects** → a four-entry allowlist of
  inert types, never `weights_only=False`, with the reason recorded and a test
  that the allowlist is exactly those four.
- **The bound could be wrong** → it is published beside the numbers, so a
  reader who disagrees can see what a different bound would have decided. What
  is not negotiable is that it was fixed before the run.
- **The incumbent that matters is not the one we expected** → the probe compared
  the candidate with both stored keys, and `clip-vit-l14` — not `dinov2-large` —
  is the one the naive statistic ranked as the rival. Every key the service
  stores image vectors under is measured, and the bound is taken against the
  best of them, not against a chosen one.
- **The answer may be "no key"**, after the work of measuring → that is the
  outcome this change is shaped to allow, and the requirement it adds makes it
  the normal one rather than a failure.

## Migration Plan

Nothing to migrate: no schema, no setting, no stored vector, no endpoint. The
follow-up change, if there is one, is where a migration appears.

## Open Questions

None that change the specs, the approach or the tasks.
