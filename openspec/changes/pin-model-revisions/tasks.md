# Tasks — pin-model-revisions

## 1. The revision reaches the weights

- [ ] 1.1 `app/core/settings.py`: `clip_revision` and `dinov2_revision`, read
  from `CLIP_REVISION` and `DINOV2_REVISION`, defaulting to the commits this
  repository verified against the hub — re-read from the hub at implementation
  time rather than copied from the proposal. Verify: unit tests that each
  default is a 40-character lowercase hex commit and that each setting is read
  from its documented environment name.
- [ ] 1.2 The binding of design decision 1, as configuration validation: a
  checkpoint name moved away from its default while its revision is left at the
  default is refused at startup, by name; an empty revision is refused too,
  because it would mean "whatever `main` is". Verify: unit tests, each watched
  to refuse — a substituted CLIP name with the default revision, the same for
  DINOv2, an empty revision, and the two legal combinations (both defaulted;
  name and revision both configured).
- [ ] 1.3 `app/ml/clip.py` and `app/ml/dinov2.py`: the revision is resolved once
  per `load` and passed to **every** `from_pretrained` call — the processor and
  the model alike (design decision 2). Verify: unit tests that record the two
  calls a stand-in receives and assert both carry the same revision, without
  loading any weights; and that neither adapter calls `from_pretrained` without
  one.
- [ ] 1.4 The real checkpoints still load and still answer. Verify: the
  `models`-suite tests for CLIP and DINOv2 pass unchanged against the pinned
  revisions (real weights, never in CI), including the width check and the
  conformance helpers they already use.

## 2. The decision, and the documents that carry it

- [ ] 2.1 The `embedding-models` delta lands as written: a checkpoint is loaded
  at a revision rather than at a name, one revision per load for every artefact
  of it, and a substituted name needs a revision of its own. Verify:
  `openspec validate --strict`; each of its three scenarios has a test.
- [ ] 2.2 `docs/adr/ADR-007-pinned-checkpoint-revisions.md`: why the revision is
  configuration rather than a constant (and why that differs from ADR-005, so
  the asymmetry is not read as an inconsistency), what one revision per load
  closes, and **what this change does not fix** — vectors stored before it have
  provenance nobody can reconstruct, and the repair is a re-index. It records
  the detection design that was dropped and why, so a later reader does not
  re-propose it blind. Verify: the ADR index carries its row.
- [ ] 2.3 `docs/reference/settings.md` gains both settings with their defaults
  and the rule that binds them to their names; `docs/how-to/models.md` says what
  to set when substituting a checkpoint. Verify: both re-read whole after the
  last edit; every command printed in the changed sections was run in that form.
- [ ] 2.4 Sweep for the claim, not the line: `rg` the repository for the two
  checkpoint names and for `from_pretrained`, and reconcile every document that
  describes how a model is chosen or loaded — including `README.md` and
  `docs/explanation/requirements.md` §2.3 if it states the name is all that
  identifies a checkpoint. Verify: every hit read, with the ones left unchanged
  named in the handoff.

## 3. Closing the change

- [ ] 3.1 A demonstrated failing input for every new or changed check (high
  tier): each default's shape, the substituted-name rule, the empty-revision
  rule, and the one-revision-per-load rule for each adapter. Verify: one table,
  one row per check, each a run with that one edit and the file restored
  afterwards.
- [ ] 3.2 Nothing observable changed. Verify: the API and integration suites
  pass unchanged — no test needed editing to accommodate this change — and the
  readiness payload, the endpoints and the schema are untouched, which the
  absence of a migration and of any diff under `alembic/`, `app/api/` and
  `app/services/` shows.
- [ ] 3.3 `openspec validate pin-model-revisions --strict` passes and every task
  above is checked with its evidence.
- [ ] 3.4 Run locally everything CI runs, in CI's own form:
  `FORCE_COLOR=1 CI=true make check`, `openspec validate --all --strict`,
  `sh -n scripts/*.sh`, every `scripts/*_test.sh`,
  `FORCE_COLOR=1 CI=true make test-integration` with the database up,
  `make audit`, and `make image`. Verify: each command's result recorded in the
  handoff.
- [ ] 3.5 Hand over for the push: `handoff.md` at `awaiting-gate-2`, the
  mechanical floor passing, and the branch ready. Verify:
  `scripts/pregate-verify.sh gate2 pin-model-revisions` prints all checks passed
  and its output is recorded in the handoff. The green CI run is the gate's
  prerequisite rather than this task's evidence, so the request waits for the
  user's push and their report of the run.
