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

**The backbone loads cleanly.** With `open_clip`'s `ViT-L-14` visual tower and
`visual.proj` removed (CSD replaces CLIP's own 1024→768 projection with its two
heads), the checkpoint's `module.backbone.*` tensors load with **0 missing and
0 unexpected**.

**The probe's numbers**, four photographs × six looks, are in `proposal.md`.

## Goals / Non-Goals

**Goals**

- A number that says whether a style key answers something `dinov2-large` does
  not, produced by a command, over a corpus that command builds.
- A decision recorded where decisions live, including the decision *not* to add
  a key.
- The rule that produced it written into the specs, so the next candidate key
  is held to it rather than to an argument.

**Non-Goals** (beyond the proposal's)

- No abstraction over "any candidate model". One candidate, one incumbent, one
  command.
- No attempt to make the benchmark reusable for text models.

## Applicability (high tier)

| Question | This change |
|---|---|
| Empty, zero and null inputs | The corpus is built from pictures the repository already holds; a look that produces a blank image (a fully posterised white photograph) would give a vector like any other, and a **zero vector** cannot be normalised — the shared guard refuses it rather than dividing into `nan`. The benchmark refuses a corpus below its minimum rather than publishing a number computed from three pictures. |
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
set of deterministic looks — grayscale, posterise, edges, painterly, sepia —
to each. Every look is a pure function of the bytes, so the corpus is
reproducible by the command, needs no download and raises no licence question.

*What this guarantees:* a ground truth nobody has to label — two pictures share
a look because the same function produced them, and share a subject because
they came from the same photograph. *What it does not:* these are filters, not
painters. The measurement is about separating *how a picture looks* from *what
is in it*, which is the property a style key is bought for; it is not evidence
about Impressionism, and the ADR will say so in those words.

*Alternative considered:* a hand-picked set of public-domain artworks. Rejected:
not reproducible by a command, and "hand-picked" is where a measurement starts
to measure the person.

### 2. One number: how far a model leans toward style

For a corpus of `pictures × looks`, two averages over unit vectors:

- **same look, different picture** — the style side;
- **same picture, different look** — the subject side.

The **leaning** is their ratio. A model that ranks by subject has a small
leaning (DINOv2: 0.145 in the probe); a model that ranks by style approaches or
exceeds 1 (CSD: 0.92).

**The bound, fixed here and before the full run: a candidate earns a key only
if its leaning is at least 3× the incumbent's** on the same corpus. Three,
because a key costs a migration, an index, a vector for every asset and a job
for every upload, and a candidate that is merely somewhat more style-aware than
a model already installed has not bought that. The probe informed *feasibility*
— that a style descriptor exists and loads — and deliberately not this number:
four pictures decide nothing, and a bound chosen after seeing the full table
would be a bound fitted to it.

Both numbers are published per model, and the per-look breakdown with them, so
a reader can see which look carried the average.

*What this guarantees:* the decision is one comparison against the thing the
service already runs. *What it does not:* it says nothing about which model
retrieves *better* for a person's actual query — that would need human judgement and
a corpus this project cannot have.

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

The numbers, the corpus it was run on with its size and its looks, the pinned
revision, the bound, and the decision — **including "no key" as a decision
with the same standing as "a key"**. Change 14 is the precedent: it measured,
decided to change nothing, and the record of that is one of the more useful
things in this repository.

## Risks / Trade-offs

- **The filters are not styles** → stated in the ADR, in the how-to and in the
  spec's own wording ("how a picture looks"), and the corpus is printed with
  its looks so a reader sees exactly what was measured.
- **A new dependency for one command** → its own group, out of the image, MIT,
  maintained (2.32.0, April 2025), and justified against the hand-written
  alternative in the proposal.
- **A training checkpoint with pickled objects** → a four-entry allowlist of
  inert types, never `weights_only=False`, with the reason recorded and a test
  that the allowlist is exactly those four.
- **The bound could be wrong** → it is published beside the numbers, so a
  reader who disagrees can see what a different bound would have decided. What
  is not negotiable is that it was fixed before the run.
- **The answer may be "no key"**, after the work of measuring → that is the
  outcome this change is shaped to allow, and the requirement it adds makes it
  the normal one rather than a failure.

## Migration Plan

Nothing to migrate: no schema, no setting, no stored vector, no endpoint. The
follow-up change, if there is one, is where a migration appears.

## Open Questions

None that change the specs, the approach or the tasks.
