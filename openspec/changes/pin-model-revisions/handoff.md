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

## What the proposal decided, after the user reshaped it

The first draft detected as well as pinned: a table recording per model key what
its vectors were built with, a fifth readiness check, a CLI escape hatch and a
migration. The user's brief for this change is **polish** — everything the
earlier changes built must keep working and keep its shape, because those are
the project's substance and this is dressing on top. Measured against that, the
first draft disqualified itself: it would have made an existing deployment go
**not-ready on upgrade** until its corpus was re-indexed. A refinement that stops
a working system is not a refinement.

So the change fixes the **cause** and leaves the consequence alone:

- **Risk-Tier: high**, and not out of caution — this project's own trigger list
  names "model downloads and any network egress", and the change edits the call
  that fetches weights. Everything else about it is small.
- **The revision is configuration with a verified default**, not a constant:
  §2.3 made the checkpoint *name* a setting on purpose so a fine-tune or a
  mirror can be substituted, and a constant would either forbid that or be
  ignored by it. ADR-007 records the asymmetry with ADR-005 so it is not read as
  an inconsistency.
- **The two settings are bound** — a substituted name with the default revision
  is refused at startup, because a commit belongs to a repository; so is an
  empty revision, which would mean "whatever `main` is".
- **One revision per load**, passed to the processor and the weights alike. That
  hole is what change 18's Gate 2 reviewer named twice.
- **Nothing observable changes.** No migration, no schema, no endpoint, no
  probe, no write path, no command, no stored vector. The defaults are the
  commits the local cache already resolved, so not a byte is downloaded here.
- **What it does not fix, stated rather than implied:** vectors stored before it
  have provenance nobody can reconstruct. The repair is a re-index, which is the
  `models migrate` wish and its own change. The detection design that was
  dropped is recorded in the design and will be in ADR-007, so a later reader
  does not re-propose it blind.

## Next step

`/gate-review pin-model-revisions 1` — Gate 1 on the artifacts.
`scripts/pregate-verify.sh gate1 pin-model-revisions` passes (13 tasks, tier
declared, applicability table present, links resolve).

## Blockers

None.
