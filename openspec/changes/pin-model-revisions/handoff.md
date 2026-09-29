# Handoff — pin-model-revisions

**Updated:** 2026-09-29 · claude
**State:** proposing
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

## Next step

`/opsx:propose pin-model-revisions`.

Questions the proposal has to answer, none of them settled yet:

- **What happens to vectors already stored** under an unpinned key? A pinned
  revision may not be the one they were computed with, and nobody can tell.
  Re-index, accept, or detect?
- **Where does the revision live** — a repository constant beside the key, a
  setting with a default, or both? A constant makes it reproducible and a
  setting makes it substitutable, and the requirements already say a compatible
  checkpoint must be substitutable without a schema change.
- **Does readiness report it?** The probe compares the application's
  declaration with the schema; it cannot currently see which weights answered.
- **Risk tier.** Likely `high`: it touches model loading and the identity of
  every stored vector, and the answer to the first question may be a re-index.

## Blockers

None.
