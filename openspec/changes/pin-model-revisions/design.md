# Design — pin-model-revisions

## Context

See `proposal.md` — Why. Three facts establish the defect, all read from the
current source:

- `app/ml/clip.py` and `app/ml/dinov2.py` both call
  `from_pretrained(name, cache_dir=cache)` **twice** — once for the processor,
  once for the weights — with no `revision`.
- `app/ml/mclip.py` passes `revision=REVISION` to every read it makes, a
  repository constant, and ADR-005 says why. The precedent exists; these two
  keys are the exception.
- `app/services/readiness.py` compares the application's declarations with the
  schema's. Nothing in it, or anywhere else, can see which weights answered.

The store holds vectors under both keys today, so this is not a rule for a
future corpus: it is a rule that finds an existing one wanting.

## Goals / Non-Goals

**Goals**

- A vector's key names one checkpoint, reproducibly, without giving up the
  substitution the requirements allow.
- A disagreement between the corpus and the configuration is loud, not silent.
- An operator who knows what their corpus was built with can say so, without
  re-indexing it.

**Non-Goals** (beyond the proposal's)

- No attempt to identify weights the service did not load itself.
- No re-indexing, scheduled or automatic.

## Applicability (high tier)

| Question | This change |
|---|---|
| Empty, zero and null inputs | A store with no vectors has no records and the check passes on nothing. A key enabled but never written has no record, and the check ignores it: there is nothing whose provenance could disagree. A key whose vectors were all deleted keeps its record — harmless, because the check requires vectors to exist — and if the key is filled again under another revision the mismatch is real and `models record` is the answer. |
| Crash around an external effect | The record is written in the transaction that stores the first vector, so a crash leaves neither the vector nor a record claiming it. The other external effect is the checkpoint download, which is unchanged except that it now names a commit. |
| Concurrent writers | Two runners can store the first vector under a key at the same moment. The record is an insert that does nothing on conflict, so one of them wins and neither fails. If those runners are configured differently — a rolling deployment mid-change — the loser's own readiness check then reports the mismatch against the record that won, which is the detection working rather than a race to paper over. |
| Idempotent retries | The queue is at-least-once (ADR-003) and an embedding write is an idempotent upsert. The record follows the same shape: insert if absent, never update, so a retried write cannot change what the corpus claims. |
| Authorization boundary | n/a — no endpoint gains or loses a caller. |
| Money and rounding | n/a. |
| Deletion and expiry | Deleting an asset deletes its embeddings and leaves the record, which the check ignores once the key holds nothing. No record expires: a corpus does not become unknown with age. |

## Decisions

### 1. The revision is configuration with a verified default

A constant would be simpler and it is what ADR-005 did for the query encoder.
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
will either refuse or, worse, resolve to something unrelated. Settings
validation refuses that combination at startup, naming the setting to fix.

*What this guarantees:* a build states which weights it runs. *What it does not:*
it does not verify that the commit is what it claims to be — the hub does that,
and what this fixes is that no commit was named at all.

### 2. One revision per load, for every artefact of it

Both adapters read two things: a processor and a model. Today each is resolved
on its own, and between them a repository can move. The revision is resolved
once at the top of `load` and passed to every read, which closes the gap by
construction rather than by timing.

*What this guarantees:* the preprocessing and the weights are from one snapshot.
*What it does not:* it says nothing about a checkpoint whose own files are
inconsistent, which is the hub's problem and not observable here.

### 3. The record is per key, written with the first vector

The store gains one row per model key: the key, the revision, and when it was
recorded. Written in the transaction that stores the **first** vector under that
key, and never updated afterwards.

*Why with the first vector rather than at load:* loading a model does not mean
storing anything, and a process that warms a model and then fails would leave a
claim about a corpus it never wrote.

*Why never updated:* a record that followed the configuration would agree with
it always, and detect nothing. It is a statement about what was stored, and what
was stored does not change.

*Why per key rather than per vector:* ADR-001 gives an embedding's identity to
the asset and the key. A revision column on `embeddings` would add a third
component to that identity, touch every write path and every read that reasons
about identity, and carry the same value on every row a key holds. The
alternative was considered and refused; ADR-007 records it, because a later
reader will ask.

*What this guarantees:* a key's vectors are described by something written when
they were written. *What it does not:* it cannot describe a corpus stored under
two revisions before the record existed — that corpus is `unknown`, below.

### 4. `unknown` is a stated absence, and it blocks

A store that already holds vectors gets a record of `unknown` for each such key,
written by the migration. Nothing can reconstruct what those vectors were built
with, and a guess written into a provenance record is worse than no record.

`unknown` equals no configured revision, so the readiness check fails on it. That
is deliberate and it is the change's sharpest edge: **an existing deployment goes
not-ready on upgrade** until its operator either re-indexes the corpus or records
what it was built with. The proposal says so under Impact rather than leaving it
to be discovered.

*Alternative considered:* treat `unknown` as a warning that does not block.
Rejected — `CheckResult` is a boolean by design, a warning channel would be new
surface, and a warning nobody is forced to read is how this defect survived
eighteen changes in the first place.

### 5. The operator can say what the corpus was built with

`semanticshelf models record <key> <revision>` writes the record for a key that
has none or replaces `unknown`. It is the operator's declaration, and it is the
only way to clear `unknown` short of re-indexing.

It cannot overwrite a record that names a real revision: that would turn the
detection off from the command line, which is the one thing the record exists to
prevent. Clearing such a record means re-indexing, which is the honest cost.

*What this guarantees:* a detection that can be cleared by someone who knows the
answer. *What it does not:* it does not check the declaration. An operator who
records the wrong commit has recorded the wrong commit; the record says who
wrote it and when.

## Risks / Trade-offs

- **Every existing deployment goes not-ready on upgrade** → stated in the
  proposal's Impact, in ADR-007 and in the how-to, with both remedies named in
  the probe's own reason text. For this repository's own corpus the remedy is
  `make demo`.
- **A new table for one row per model** → small, and the alternative (a column
  on `embeddings`) is the one ADR-001 forbids by giving identity to the key.
- **The operator's declaration is unverified** → it is a declaration; it is
  recorded with its timestamp, and it cannot overwrite a real record.
- **The revision defaults could go stale** → they are the commits the repository
  verified, and a checkpoint that moves does not change what a default names.
  A later change that upgrades a model changes the default, which is a re-index
  and a new record — exactly the event this change makes visible.

## Migration Plan

One Alembic revision: create the table, then insert `unknown` for every model
key that already has rows in `embeddings`. Downgrade drops the table; no vector
is read, written or moved in either direction.

## Open Questions

None that change the specs, the approach or the tasks.
