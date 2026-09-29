# ADR-007: a model key names a commit, and what that still cannot say

**Date:** 2026-09-29
**Status:** accepted
**Related:** ADR-001 (an embedding's identity is its asset and its model key); ADR-005 (the query encoder, pinned by constant, and the precedent this follows); ADR-006 (the measurement whose reviewers found this); authored by the OpenSpec change `pin-model-revisions`

## Context

The `model` column is part of an embedding's identity: vectors of different
models are never compared, and the key is what says which model a vector came
from. The key did not keep that promise.

`clip-vit-l14` and `dinov2-large` loaded a checkpoint **name** — a setting, with
no revision — and each adapter resolved its processor and its weights in two
separate `from_pretrained` calls. So the same key could mean different weights
on two machines, or on the same machine a month apart, and the two calls could
even disagree with each other. No width check sees it: the width does not
change.

It was found from the outside. Change 18 set out to publish a measurement
anyone could re-run, and its reviewers made the same objection three times, each
time about a different sentence: a cache of vectors could not be trusted, then a
scan of the model cache could not identify what had answered, then "the same
machine" could not stand as a condition for reproducing a table. Every one of
those was this defect, seen from a different angle.

ADR-005 had pinned the query encoder's revision one change earlier, for exactly
this reason. These two keys were simply never pinned.

## Decision

**A checkpoint is read at a commit.** `CLIP_REVISION` and `DINOV2_REVISION`
default to the commits this repository verified —
`32bd64288804d66eefd0ccbe215aa642df71cc41` and
`47b73eefe95e8d44ec3623f8890bd894b6ea2d6c` — and the revision is resolved once
per load and handed to every read that load makes.

**Configuration, not a constant** — which is where this differs from ADR-005,
deliberately. §2.3 of the requirements made the checkpoint *name* a setting on
purpose: a compatible fine-tune or a mirror must be substitutable without a
schema change, since it is the same space and the same width. A revision fixed
in the source would either forbid that or be ignored by it. The query encoder
has no such setting, so a constant was right there and is wrong here. The
asymmetry is deliberate and this paragraph exists so it is not read as an
oversight.

**A revision is a full 40-character lowercase commit, or the service refuses to
start.** The model hub accepts a branch or a tag wherever it accepts a commit,
so `CLIP_REVISION=main` would read as pinned and pin nothing — worse than the
unpinned load it replaced, because it looks solved. An abbreviated hash is
refused too: it is a prefix, and a repository may grow a second object sharing
it. The refusal breaks no deployment, because the setting did not exist before.

**A substituted name inherits no revision, and is not refused.** A default
commit belongs to the default repository; applying it to a checkpoint someone
substituted would name a commit of a repository that was replaced. Such a
checkpoint is therefore read the way every checkpoint was read before this
record — with no `revision` argument at all — and the service logs that it is
unpinned. It is **not** refused: that configuration works today, and a change
whose brief is reproducibility may not make a working deployment stop. An
operator who wants it pinned sets its revision, which is one line.

## Alternatives considered

**A constant beside the key, as ADR-005 has.** Rejected: it would forbid the
substitution §2.3 requires, or be silently ignored by it.

**Refusing to start when a substituted name carries no revision.** Rejected: it
refuses a configuration the service accepts today. The first draft of this
change did exactly that, and the Gate 1 reviewer was right to call the
compatibility promise beside it contradictory.

**Resolving the current commit from the hub when none is configured**, so every
load is pinned to something. Rejected: it puts a network call on a path that
must work from a warm cache with no network, and its fallback when that call
fails is the unpinned load anyway — a guarantee that holds only while the
network is up, bought with a new way for a load to be slow or to fail.

**Recording, per model key, what a corpus's vectors were built with, and
refusing readiness when that disagrees with the configuration.** This was
designed in full and dropped. It needs a migration, a table, a change to the
embedding write path and a fifth readiness check — and it makes an existing
deployment go not-ready on upgrade until its corpus is re-indexed or vouched
for. For a change whose brief is polish, that is disqualifying: a refinement
that stops a working system is not a refinement. It is written down here so a
later reader does not re-propose it believing nobody weighed it.

**A revision column on `embeddings`.** Rejected: it would make the revision part
of an embedding's identity, which ADR-001 gives to the asset and the key, and it
would carry the same value on every row a key holds.

## Consequences

**A key names one checkpoint from here on.** Two loads of a default
configuration, a year apart, read the same weights, and the weights and the
preprocessing of a pinned load come from one snapshot.

**What this does not fix, and cannot.** Vectors stored before this change were
built with whatever the name resolved to at the time, and nothing can
reconstruct what that was. They may have been built under two different
revisions. The service does not detect it, by the decision above, and the only
repair is a re-index — which is the `models migrate <old-key> <new-key>` wish in
§9 of the requirements, its own change. A corpus whose provenance matters should
be re-indexed once after this change and not before.

**A substituted checkpoint stays as unpinned as it was** unless its operator
pins it. The service says so at load; the how-to asks for it.

**Upgrading changes nothing observable.** No migration, no schema, no endpoint,
no probe, no stored vector, and no download on a machine whose cache already
holds these commits. Every configuration the service accepted before it accepts
after.

**A model upgrade is now a visible event.** Changing a default revision is a
diff in this repository, and it means a re-index — which is exactly the event
that used to happen silently.

## Supersedes

No ADR clause. ADR-001's rule that an embedding's identity is its asset and its
key is what makes this record necessary, and is unchanged by it.
