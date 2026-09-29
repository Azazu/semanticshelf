# Proposal — pin-model-revisions

**Risk-Tier:** high

Three triggers: the change **adds a migration** and a table, it changes how
**model weights are downloaded** — network egress from a process this repository
ships — and it gives the readiness probe a new way to refuse traffic, which is
verifier-adjacent infrastructure. Gate 1 before implementation, a demonstrated
failing input for every new check.

## Why

The `model` column is part of an embedding's identity (ADR-001): vectors of
different models are never compared, and the key is what says which model a
vector came from. The key does not keep that promise.

`clip-vit-l14` and `dinov2-large` load a checkpoint **name** that is a setting
(`CLIP_MODEL_NAME`, `DINOV2_MODEL_NAME`) with **no revision**, and each adapter
resolves its weights and its processor in two separate `from_pretrained` calls.
So:

- the same key can mean different weights on two machines, or on the same
  machine a month apart, and **a stored vector cannot be reproduced from its
  key**;
- a corpus indexed across such a change ranks against itself, silently — no
  width check sees it, because the width does not change;
- the two calls can disagree with each other, pairing weights from one snapshot
  with a processor from another.

This is not hypothetical. Change 18's reviewers found it while trying to make a
published measurement reproducible, and it forced three successive narrowings of
what that record could claim. ADR-005 pinned the query encoder's revision for
exactly this reason a change earlier; these two keys were simply never pinned,
and the repository is inconsistent with its own precedent.

## What Changes

**Pinned, and the disagreement made visible.**

- **A revision beside every checkpoint name.** `CLIP_REVISION` and
  `DINOV2_REVISION`, settings with defaults that are the commits this
  repository verified. Resolved once per load and passed to **both**
  `from_pretrained` calls, so weights and processor cannot come from different
  snapshots. Configuration refuses a checkpoint name that is not the default
  one without a revision to go with it: a commit belongs to a repository.
- **The store records what its vectors were built with.** A new table, one row
  per model key, written in the same transaction as the first embedding stored
  under that key. Not per vector — that would make the revision part of an
  embedding's identity, which ADR-001 reserves for the key.
- **Readiness refuses when the corpus and the configuration disagree.** A fifth
  check: for every enabled storage model whose vectors the store holds, the
  recorded revision against the configured one. A mismatch is a 503 naming both
  and the remedy, instead of a service that silently ranks incomparable vectors.
- **A corpus from before this change is `unknown`, and says so.** The migration
  records `unknown` for every key that already holds vectors, because nobody can
  say what they were built with. `unknown` fails the check too — with its own
  reason and its own two remedies.
- **`semanticshelf models record <key> <revision>`** — the operator's
  declaration, so `unknown` can be resolved by someone who knows the answer
  rather than only by re-indexing the whole corpus.
- **ADR-007** records why the revision is a setting rather than a constant, why
  the record is per key rather than per vector, and why `unknown` blocks.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `embedding-models`: a checkpoint is loaded at a pinned revision, one revision
  for the weights and the processor alike, and a substituted name needs a
  revision of its own.
- `embedding-storage`: the store records which revision each key's vectors were
  built with, and that record is written with the first vector rather than
  claimed afterwards.
- `health-probes`: readiness gains a fifth check and refuses when the corpus's
  provenance and the configuration disagree.

## Impact

- **New:** an Alembic migration and a table; `app/repositories/` gains the
  record; a readiness check; a CLI subcommand; `docs/adr/ADR-007-*.md`; unit,
  integration and API tests.
- **Changed:** `app/ml/clip.py`, `app/ml/dinov2.py` (the load path),
  `app/core/settings.py` (two settings and their validation),
  `app/services/readiness.py`, `app/services/indexing.py` or the embedding
  repository (the write path), `openspec/specs/*` deltas,
  `docs/reference/settings.md`, `docs/reference/commands.md`,
  `docs/how-to/models.md`, `README.md` if it names the checks.
- **Unchanged:** the vectors themselves, the `embeddings` table's columns, the
  dimension constraint, the indexes, both search endpoints and the query
  encoder — `mclip-xlmr-l14` is already pinned and stores nothing.
- **Operational:** a deployment that upgrades **will** go not-ready until its
  corpus's provenance is recorded or re-indexed. That is the point of the
  change, and it is stated here rather than discovered.

## Non-goals

- **No revision per vector.** A column on `embeddings` would make the revision
  part of an embedding's identity, which ADR-001 gives to the key alone, and it
  would touch every write path for a fact that is the same for every row a key
  holds. Considered and refused; the record is per key.
- **No re-indexing tooling.** `models migrate <old-key> <new-key>` is its own
  wish in §9 of the requirements and its own change. This one detects; it does
  not repair.
- **No automatic re-index** on a mismatch. A service that quietly re-embeds a
  corpus because a setting changed is worse than one that stops.
- **No change to the query encoder.** `mclip-xlmr-l14` is pinned by constant
  already and stores no vector, so there is nothing to record and nothing to
  compare.
- **No verification that a revision is what it claims.** A commit hash is
  checked by the hub, not here; what this change fixes is that no commit was
  named at all.
