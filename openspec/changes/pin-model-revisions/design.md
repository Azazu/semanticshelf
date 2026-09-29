# Design — pin-model-revisions

## Context

See `proposal.md` — Why. Three facts establish the defect, all read from the
current source:

- `app/ml/clip.py` and `app/ml/dinov2.py` both call
  `from_pretrained(name, cache_dir=cache)` **twice** — once for the processor,
  once for the weights — with no `revision`.
- `app/ml/mclip.py` passes `revision=REVISION` to every read it makes, and
  ADR-005 says why. The precedent exists; these two keys are the exception.
- The commits the local cache resolved for both names are the commits the hub's
  `main` points at today: `32bd6428…` and `47b73eef…`. Pinning them changes
  which weights answer on this machine not at all.

**This change is polish.** Everything the earlier changes built stays as it is
and keeps behaving as it does: no migration, no schema, no endpoint, no probe,
no write path, no stored vector, no command. What it fixes is one thing — that a
model key names a moving target — and it fixes it where the target moves.

## Goals / Non-Goals

**Goals**

- A key names one checkpoint, reproducibly, without giving up the substitution
  the requirements allow.
- Nothing that worked yesterday behaves differently today.

**Non-Goals** (beyond the proposal's)

- No attempt to identify weights the service did not load itself.
- No new failure mode. A change whose point is reproducibility must not make a
  working deployment stop.

## Applicability (high tier)

| Question | This change |
|---|---|
| Crash around an external effect | The only external effect is the checkpoint download, and it is unchanged except that it now names a commit. A failed download leaves the adapter unbuilt, exactly as before, and nothing has been stored. |
| Empty, zero and null inputs | An empty revision setting is the absence of a value, not a revision: configuration refuses it rather than passing it to the hub, where an empty string would silently mean "whatever `main` is" — the defect this change exists to remove. |
| Idempotent retries | Loading is already idempotent per process (the registry caches the built embedder), and a revision does not change that. A retried load reads the same commit. |
| Authorization boundary | n/a — no endpoint gains or loses a caller. |
| Concurrent writers | n/a — nothing is written. |
| Money and rounding | n/a. |
| Deletion and expiry | n/a — no record is created, so none can go stale. |

## Decisions

### 1. The revision is configuration with a verified default

A constant would be simpler, and it is what ADR-005 did for the query encoder.
It is wrong here, because §2.3 of the requirements deliberately made the
checkpoint *name* a setting: a fine-tune or a mirror must be substitutable
without a schema change, since it is the same space and the same width. A
revision fixed in the source would either forbid that or be ignored by it.

So `CLIP_REVISION` and `DINOV2_REVISION` are settings, defaulting to the commits
this repository verified. A deployment that configures nothing is reproducible;
a deployment that substitutes a checkpoint says which commit of it.

**And the two settings are bound together.** A revision is a commit *of a
repository*. A name configured away from its default while the revision stays at
the default names a commit of the repository that was replaced — which the hub
will either refuse or, worse, resolve to something unrelated. Configuration
refuses that combination at startup, naming the setting to fix. The same
validation refuses an empty revision, which would mean "whatever `main` is".

*What this guarantees:* a build states which weights it runs. *What it does not:*
it does not verify that the commit is what it claims to be — the hub does that,
and what this fixes is that no commit was named at all.

*Alternative considered:* a constant beside the key, as ADR-005 has. Rejected
for the substitution requirement above — and ADR-007 records the asymmetry, so
the next reader does not read it as an inconsistency.

### 2. One revision per load, for every artefact of it

Both adapters read two things: a processor and a model. Today each is resolved
on its own, and between them a repository can move. The revision is resolved
once at the top of `load` and passed to every read, which closes the gap by
construction rather than by timing.

*What this guarantees:* the preprocessing and the weights are from one snapshot.
*What it does not:* it says nothing about a checkpoint whose own files are
inconsistent, which is the hub's problem and not observable here.

### 3. What this change refuses to do, and why that is a decision

Recording per model key what a corpus's vectors were built with, and refusing
readiness when that disagrees with the configuration, would turn a silent
problem into a loud one. It was designed in full and dropped, for a reason worth
writing down rather than leaving as an omission:

- it needs a migration and a table — the data model is part of what this project
  shows, and ADR-001 gives an embedding's identity to the asset and the key;
- it changes the embedding write path, which is the core of the indexing work;
- it gives the readiness probe a new way to refuse traffic, and **an existing
  deployment would go not-ready on upgrade** until its corpus was re-indexed or
  vouched for.

That last one is disqualifying on its own for a change whose brief is polish: a
refinement that makes a working system stop is not a refinement. So this change
fixes the **cause** — a key that names a moving target — and leaves the
**consequence** for vectors already stored to the tooling that can actually
repair it, `models migrate`, which is its own wish and its own change.

*What this guarantees:* nothing observable changes. *What it does not:* vectors
stored before this change still have provenance nobody can reconstruct. ADR-007
states that in those words, because a record that quietly implies otherwise
would be worse than the defect.

## Migration Plan

None. No schema, no data, no setting whose absence changes behaviour: both new
settings have defaults that are the commits already in use.

## Open Questions

None that change the specs, the approach or the tasks.
