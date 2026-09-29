# Handoff — pin-model-revisions

**Updated:** 2026-09-29 · claude
**State:** awaiting-gate-2
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

## Demonstrated failing inputs (high tier, task 3.1)

Each guard removed on its own, the covering test run, the file restored.

| check | file | test | with the guard removed |
|---|---|---|---|
| each default revision is a full commit | `app/core/settings.py` | `-k default_revision_is_a_full_commit` | FAILED |
| a revision that is not a commit is refused | `app/core/settings.py` | `-k not_a_commit_is_refused` | FAILED |
| a substituted name inherits no revision | `app/core/settings.py` | `-k inherits_no_revision` | FAILED |
| an explicitly configured revision wins | `app/core/settings.py` | `-k whatever_the_name_says` | FAILED |
| the text model hands one revision to both reads | `app/ml/clip.py` | `::test_a_pinned_load_hands_one_revision_to_both_reads` | FAILED |
| the text model unpinned carries no revision | `app/ml/clip.py` | `::test_an_unpinned_load_hands_neither_read_a_revision` | FAILED |
| the picture model hands one revision to both reads | `app/ml/dinov2.py` | `-k picture_model_pinned` | FAILED |
| the picture model unpinned carries no revision | `app/ml/dinov2.py` | `-k picture_model_unpinned` | FAILED |
| an unpinned load says so | `app/ml/base.py` | `-k unpinned_load_says_so` | FAILED |

Two of these read `passed` on the first run, and the run was wrong rather than
the guard: the `-k` expression for each CLIP case is a substring of the DINOv2
test's name, so the plant in `clip.py` was checked by a test of `dinov2.py`.
Re-run against exact node ids, both fail. A demonstration that selects the wrong
test proves nothing, which is the point of doing them one at a time.

## Nothing observable changed (task 3.2)

```console
$ git diff main --stat -- alembic app/api app/services ui
(no output)
```

The whole diff against `main` is `app/core/settings.py`, the three `app/ml`
modules, four documents, and **one new test file** — no existing test needed
editing to accommodate the change, which is the evidence that no behaviour it
covers moved.

## What CI runs, run locally (task 3.4)

| command | result |
|---|---|
| `FORCE_COLOR=1 CI=true make check` | **green** — 850 passed |
| `openspec validate --all --strict` | **green** — 17 passed |
| `sh -n scripts/*.sh` | **green** — 7 files |
| `scripts/gate_run_test.sh` | **green** — 77 passed |
| `scripts/workflow_verify_test.sh` | **green** — 23 passed |
| `FORCE_COLOR=1 CI=true make test-integration` | **green** — 296 passed |
| `make audit` | **green** — no known vulnerabilities in 97 packages |
| `make image` | **green** — `semanticshelf:runtime` 1.79 GB, unchanged |
| `uv run pytest -m models` (CLIP and DINOv2, real weights) | **green** — 14 passed at the pinned revisions |

Both commands the how-to prints were run in that form: `models warm` loads at the
pinned revisions, and `CLIP_REVISION=main` is refused at startup by name.

## The mechanical floor for Gate 2 (task 3.5)

```console
$ scripts/pregate-verify.sh gate2 pin-model-revisions
[OK]   git diff --check clean
[OK]   openspec validate pin-model-revisions --strict
[OK]   risk tier declared: high
[OK]   proposal.md has a Non-goals section
[OK]   tasks.md has 14 task(s)
[OK]   every task checked
[OK]   checked-task referenced paths exist
[OK]   markdown links resolve (11 changed .md files)
[OK]   make check green
pregate-verify: gate2 pin-model-revisions — all checks passed (0 warning(s))
```

## Next step

**Gate 1 is passed** — confirmation 2 on `b633571` confirms both findings.

The user pushes `change/pin-model-revisions` and reports the CI run; then
`/gate-review pin-model-revisions 2` — Gate 2 on the code diff.
`scripts/pregate-verify.sh gate1 pin-model-revisions` passes (13 tasks, tier
declared, applicability table present, links resolve).

## Blockers

None.
