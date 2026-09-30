# Proposal — pin-model-revisions

**Risk-Tier:** high

One trigger, and it is on this project's own list: the change touches **model
downloads** — how the weights a key names are fetched. Nothing else about it is
large: no migration, no schema, no endpoint, no stored vector. Gate 1 before
implementation, a demonstrated failing input for every new check.

## Why

The `model` column is part of an embedding's identity (ADR-001): vectors of
different models are never compared, and the key is what says which model a
vector came from. The key does not keep that promise.

`clip-vit-l14` and `dinov2-large` load a checkpoint **name** that is a setting
(`CLIP_MODEL_NAME`, `DINOV2_MODEL_NAME`) with **no revision**, and each adapter
resolves its weights and its processor in two separate `from_pretrained` calls.
So the same key can mean different weights on two machines, or on the same
machine a month apart, and the two calls can even disagree with each other —
pairing weights from one snapshot with preprocessing from another. No width
check sees it, because the width does not change.

This is not hypothetical. Change 18's reviewers found it while trying to make a
published measurement reproducible, and it forced three successive narrowings of
what that record could claim. ADR-005 pinned the query encoder's revision for
exactly this reason a change earlier; these two keys were simply never pinned,
and the repository is inconsistent with its own precedent.

## What Changes

**The cause is fixed, and nothing else moves.**

- **A revision beside every checkpoint name.** `CLIP_REVISION` and
  `DINOV2_REVISION`, settings with defaults that are the commits this repository
  verified against the hub: `32bd64288804d66eefd0ccbe215aa642df71cc41` for
  `openai/clip-vit-large-patch14` and `47b73eefe95e8d44ec3623f8890bd894b6ea2d6c`
  for `facebook/dinov2-large`.
- **One revision per load, for every artefact of it** — for every load that has
  a revision. Resolved once and passed to both `from_pretrained` calls, so the
  weights and the processor cannot come from different snapshots. A load left
  unpinned by the rule below passes no revision to either call and keeps today's
  behaviour, gap included.
- **A revision has to be a commit.** The hub accepts a branch or a tag wherever
  it accepts a commit, so `CLIP_REVISION=main` would look pinned and pin
  nothing. Configuration requires a full 40-character hexadecimal commit and
  refuses a branch, a tag, an abbreviated hash or an empty value, by name. The
  setting did not exist before, so nothing that worked is refused.
- **A revision belongs to the repository it is a commit of.** A checkpoint name
  moved away from its default does **not** inherit the default revision: that
  commit belongs to the repository that was replaced. Such a checkpoint is
  loaded as it is loaded today — without a revision — and the service says so.
  It is not refused: that configuration works now and keeps working.
- **ADR-007** records why the revision is configuration rather than a constant,
  what this fixes and — as plainly — what it does not.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `embedding-models`: a checkpoint is loaded at an immutable commit, one
  revision for the weights and the processor alike wherever a load has one, and
  a substituted name inherits no revision — it loads unpinned, as it does today,
  and says so.

## Impact

- **New:** `docs/adr/ADR-007-pinned-checkpoint-revisions.md`, unit tests for the
  settings rule and for the one-revision-per-load rule, a `models`-suite test
  that both adapters still load against the real checkpoints.
- **Changed:** `app/core/settings.py` (two settings and their validation),
  `app/ml/clip.py` and `app/ml/dinov2.py` (the load path),
  `docs/reference/settings.md`, `docs/how-to/models.md`.
- **Unchanged, deliberately:** the database, every migration, the `embeddings`
  table and its constraint, the indexes, both search endpoints, the readiness
  probe's checks and payload, the indexing queue and its write path, the CLI's
  existing commands, and every vector already stored. **Every configuration the
  service accepts today it still accepts**, including a substituted checkpoint
  name with no revision — that one loads unpinned, as it does now, and says so.
  The only configurations refused are ones that could not exist before, because
  the settings that express them are new. Nothing goes not-ready, nothing
  re-indexes.
- **Downloads:** none on a machine whose cache already holds those commits,
  which is the case here — the pinned defaults are the commits the local cache
  resolved. A machine that holds a different commit fetches the pinned one once.

## Non-goals

- **No detection of a corpus built with other weights.** The obvious next step —
  recording per model key what its vectors were built with, and refusing
  readiness when that disagrees with the configuration — was designed and
  deliberately dropped. It needs a migration, a table, a change to the embedding
  write path and a fifth readiness check, and it makes an existing deployment
  go not-ready on upgrade until its corpus is re-indexed or vouched for. This
  change fixes the **cause**; the consequence for vectors already stored is not
  something it can repair, and ADR-007 says so instead of pretending.
- **No re-indexing tooling.** `models migrate <old-key> <new-key>` is its own
  wish in §9 of the requirements and its own change.
- **No revision per vector.** A column on `embeddings` would put the revision
  into an embedding's identity, which ADR-001 gives to the asset and the key.
- **No change to the query encoder.** `mclip-xlmr-l14` is pinned by constant
  already and stores no vector.
- **No verification that a revision is what it claims.** A commit hash is
  checked by the hub; what this change fixes is that no commit was named at all.
  Nor does it ask the hub whether a configured commit exists: that is a network
  call on a path that must work from a warm cache.
- **No pinning of a substituted checkpoint the operator has not pinned.** The
  documentation asks for a revision beside a substituted name; if it is not
  given, that checkpoint stays as unpinned as it is today. Refusing to start
  instead was designed and dropped — it would refuse a configuration that works
  now, which is the one thing this change may not do.
- **No upgrade of either checkpoint.** The pinned defaults are the commits this
  repository already runs, so the weights that answer today are the weights that
  answer after the change.
