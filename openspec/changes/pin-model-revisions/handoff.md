# Handoff — pin-model-revisions

**Updated:** 2026-09-29 · claude
**State:** awaiting-gate-1
**Branch:** change/pin-model-revisions

## Done this session

- Branch `change/pin-model-revisions` created off `main`, which carries changes
  0–18 archived, including `stretch-style-search` and ADR-006.
- Change scaffolded with `openspec new change` (schema `spec-driven`).
- `openspec/ROADMAP.md` already carries this as row 20 — left as it is.

## The defect this change exists for

Found by the Gate 1 and Gate 2 reviewers of change 18, where it forced three
successive narrowings of what the published measurement could claim.

`clip-vit-l14` and `dinov2-large` load a checkpoint **name** that is a setting
(`CLIP_MODEL_NAME`, `DINOV2_MODEL_NAME`), with **no revision**, and each adapter
resolves its weights and its processor in two separate `from_pretrained` calls.
Three consequences, in order of how much they matter:

1. **A stored vector cannot be reproduced from its model key.** The `model`
   column is part of an embedding's identity (ADR-001), and the same key can
   mean different weights on two machines, or on the same machine a month
   apart. Nothing detects it, and a corpus embedded half under one revision and
   half under another ranks against itself.
2. **The two calls can disagree with each other**, loading weights from one
   snapshot beside a processor from another.
3. **ADR-005 already pinned the query encoder's revision for exactly this
   reason**, and these two keys were never pinned — so the repository is
   inconsistent with its own precedent.

## What the proposal decided

- **Risk-Tier: high** — a migration, network egress from a process this
  repository ships, and a new way for readiness to refuse traffic.
- **The revision is configuration with a verified default**, not a constant:
  §2.3 made the checkpoint *name* a setting on purpose, so a fine-tune or a
  mirror can be substituted, and a constant would either forbid that or be
  ignored by it. The two settings are bound — a substituted name with the
  default revision is refused at startup, because a commit belongs to a
  repository.
- **One revision per load**, passed to the processor and the weights alike, so
  they cannot come from different snapshots. That hole is what the Gate 2
  reviewer of change 18 named twice.
- **The record is per key, not per vector** — you chose "pin and detect". A
  column on `embeddings` would put the revision into an embedding's identity,
  which ADR-001 gives to the asset and the key; the alternative is written down
  in the design and will be in ADR-007, because a later reader will ask.
- **`unknown` blocks.** A store that already holds vectors gets `unknown` for
  those keys, and no configured revision equals it — so **an existing
  deployment goes not-ready on upgrade**. That is the sharp edge of the shape
  you picked, and it is stated in the proposal's Impact rather than left to be
  discovered. For this repository's own corpus the remedy is `make demo`.
- **`semanticshelf models record <key> <revision>`** is the way out that is not
  a re-index: it clears `unknown`, and it refuses to overwrite a record naming a
  real revision — turning the detection off from the command line is the one
  thing the record exists to prevent.

## Next step

`/gate-review pin-model-revisions 1` — Gate 1 on the artifacts.

## Blockers

None.
