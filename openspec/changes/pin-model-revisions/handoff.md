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
- **A configured revision must be an immutable commit** — a branch, a tag, an
  abbreviated hash or an empty value is refused at startup by setting name,
  because each of them resolves at load time, which is the defect itself. That
  refusal breaks nothing: the setting did not exist before. *(This supersedes
  the first draft's rule that a substituted name with the default revision is
  refused — see the Gate 1 section below.)*
- **One revision per load**, passed to the processor and the weights alike —
  for every load that has a revision. That hole is what change 18's Gate 2
  reviewer named twice. A load left unpinned by the rule below keeps today's
  behaviour, gap included, and the artifacts say so rather than promising over
  it.
- **Nothing observable changes.** No migration, no schema, no endpoint, no
  probe, no write path, no command, no stored vector. The defaults are the
  commits the local cache already resolved, so not a byte is downloaded here.
- **What it does not fix, stated rather than implied:** vectors stored before it
  have provenance nobody can reconstruct. The repair is a re-index, which is the
  `models migrate` wish and its own change. The detection design that was
  dropped is recorded in the design and will be in ADR-007, so a later reader
  does not re-propose it blind.

## Gate 1 round 1: two findings, both fixed

**1. The pin would not have pinned (major).** `CLIP_REVISION=main` passed the
validation as drafted — non-empty, name at its default — and the model hub takes
a branch or a tag wherever it takes a commit. The same string handed to two
calls resolves twice, so the defect would have survived, disguised as fixed.
Configuration now requires a full 40-character hexadecimal commit and refuses a
branch, a tag, an abbreviated hash, an empty value or whitespace, by setting
name. That refusal breaks nothing: the setting did not exist before.

**2. The compatibility promise contradicted the design (major).** A deployment
that today sets only `CLIP_MODEL_NAME` starts; under the first draft it would
have inherited the default revision and been refused. So "nothing is refused
that was accepted yesterday" could not stand beside the rule as written.

Resolved by the principle this change was reshaped around rather than by
narrowing the promise: **a substituted name inherits no revision and is not
refused.** It loads without one, exactly as it does today, and the service says
it is unpinned. Refusing was designed and dropped, and so was resolving the
current commit from the hub at load time — that one adds a network call to a
path that must work from a warm cache, and its fallback is the unpinned load
anyway. Both alternatives are recorded in the design so neither is re-proposed
as an oversight.

The tasks gained the verification the reviewer asked for, including a settings
test for the pre-upgrade shape of a substituted deployment, which must start
rather than refuse.

**Confirmation 1 confirmed finding 1 and returned finding 2**, and it was right
to: the rule had changed and six siblings still carried the old one. Task 1.4
demanded that no adapter ever call `from_pretrained` without a revision, while
task 1.3 required exactly that for the unpinned case; the delta's default-revision
scenario covered "no revision configured", which includes the substituted name it
elsewhere leaves unpinned; the same-snapshot scenario and design decision 2
promised snapshot identity unconditionally; the proposal's Capabilities and task
2.1 still said a substituted name needs a revision of its own; and this handoff
still presented the startup refusal as a decision.

All of them now scope the guarantee to a load that **has** a revision, and name
the unpinned load as the case that keeps today's behaviour — including its gap.
Fix the claim, not the line: the rule was right after the first fix and the
artifacts were not.

## Next step

`/gate-review pin-model-revisions 1` — Gate 1 on the artifacts.
`scripts/pregate-verify.sh gate1 pin-model-revisions` passes (13 tasks, tier
declared, applicability table present, links resolve).

## Blockers

None.
