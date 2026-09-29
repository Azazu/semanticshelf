# Tasks — pin-model-revisions

## 1. The revision reaches the weights

- [ ] 1.1 `app/core/settings.py`: `clip_revision` and `dinov2_revision`, with
  the commits this repository verified as defaults
  (`32bd64288804d66eefd0ccbe215aa642df71cc41` for
  `openai/clip-vit-large-patch14`, `47b73eefe95e8d44ec3623f8890bd894b6ea2d6c`
  for `facebook/dinov2-large` — both re-read from the hub at implementation
  time rather than copied from here). Verify: unit tests that each default is a
  40-character hex commit, and that the settings are read from the environment
  under the documented names.
- [ ] 1.2 The binding of decision 1: a checkpoint name configured away from its
  default while its revision is left at the default is refused at startup, by
  name. Verify: unit tests, each watched to refuse — a substituted CLIP name
  with the default revision, the same for DINOv2, and the two combinations that
  are legal (both defaulted; both configured).
- [ ] 1.3 `app/ml/clip.py` and `app/ml/dinov2.py`: the revision is resolved once
  per `load` and passed to **every** `from_pretrained` call — the processor and
  the model alike (decision 2). Verify: unit tests that both calls receive the
  same revision, with the loader's two calls recorded by a stand-in rather than
  by loading weights; a `models`-suite test that each adapter still loads and
  still produces vectors of its declared width against the real checkpoint.

## 2. What the store remembers

- [ ] 2.1 An Alembic migration: a table of one row per model key — the key, the
  revision, and when it was recorded — and an insert of `unknown` for every key
  that already has rows in `embeddings` (design decision 4). Verify: the
  integration suite migrates up and down; a test that a store with vectors gets
  `unknown` for exactly those keys and nothing for the others; `make migrate`
  run against the real database.
- [ ] 2.2 The repository for it: read the record for a key, and insert one if
  absent — never update (design decision 3). Verify: integration tests that a
  second insert does not change the first, that two concurrent inserts leave one
  row and neither fails, and that reading a key with no record answers "none"
  rather than raising.
- [ ] 2.3 The write path: storing the **first** embedding under a key records
  the revision the embedder was loaded at, in the same transaction. Verify: an
  integration test that the record appears with the first vector and not before;
  one that a crash between the two leaves neither (the transaction rolls back);
  one that a retried write does not change the record.
- [ ] 2.4 The embedder tells the write path which revision it was loaded at.
  Verify: a unit test that the deterministic stand-in carries one too, so the
  whole suite exercises the same path as the real adapters.

## 3. Readiness refuses a corpus it cannot vouch for

- [ ] 3.1 The fifth check of the `health-probes` delta: for every enabled
  storage model whose key the store holds vectors under, the recorded revision
  against the configured one. `ok`, or a reason naming the key and both
  revisions; `unknown` names the key and says the provenance was never
  recorded. It loads no model and quotes no path. Verify: unit tests of the
  comparison on hand-made records — agreement, disagreement, `unknown`, a key
  with a record but no vectors, and a key with vectors but no record.
- [ ] 3.2 The check is wired into the probe beside the other four, skipped with
  the same reason when the database check failed, and inside the same time
  budget. Verify: API tests for the payload in both shapes (200 with five
  checks `ok`; 503 with `checks.revisions` naming the key), and one that the
  reason carries no path, host, user or credential.
- [ ] 3.3 Every document that lists the checks is reconciled: the readiness
  requirement is already in the delta; `docs/reference/*`, `docs/how-to/*` and
  `README.md` are swept for the four-check list and the shape of the payload.
  Verify: `rg` over the repository for the check names and for `"media": "ok"`,
  with every hit read and reconciled.

## 4. The operator's way out

- [ ] 4.1 `semanticshelf models record <key> <revision>`: writes the record for
  a key that has none and replaces `unknown`; refuses to overwrite a record that
  names a real revision, and says why (design decision 5). Verify: integration
  tests for all three cases, each watched to refuse or to write; a unit test
  that the key must be one the schema allows.
- [ ] 4.2 `docs/reference/commands.md` and `docs/how-to/models.md` carry the
  command in its exact form, what `unknown` means, and both remedies. Verify:
  every command in the changed sections was run in the form printed.

## 5. The decision

- [ ] 5.1 `docs/adr/ADR-007-pinned-checkpoint-revisions.md`: why the revision is
  configuration rather than a constant, why the record is per key rather than
  per vector, why `unknown` blocks readiness rather than warning, and what the
  operator's declaration does and does not establish. It names ADR-001 (identity
  is the asset and the key) and ADR-005 (the precedent it follows). Verify: the
  ADR index carries its row; `openspec validate --strict`.
- [ ] 5.2 `docs/reference/settings.md` gains both settings with their defaults
  and the rule that binds them to their names. Verify: re-read whole after the
  last edit.

## 6. Closing the change

- [ ] 6.1 A demonstrated failing input for every new or changed check (high
  tier): the two settings' validation, the one-revision-per-load rule, the
  record's insert-if-absent, the first-vector transaction, each branch of the
  readiness comparison, and the CLI's refusal to overwrite a real record.
  Verify: one table, one row per check, each a run with that one edit and the
  file restored afterwards.
- [ ] 6.2 `openspec validate pin-model-revisions --strict` passes and every task
  above is checked with its evidence.
- [ ] 6.3 Run locally everything CI runs, in CI's own form:
  `FORCE_COLOR=1 CI=true make check`, `openspec validate --all --strict`,
  `sh -n scripts/*.sh`, every `scripts/*_test.sh`,
  `FORCE_COLOR=1 CI=true make test-integration` with the database up,
  `make audit`, and `make image`. Verify: each command's result is recorded in
  the handoff.
- [ ] 6.4 Hand over for the push: `handoff.md` at `awaiting-gate-2`, the
  mechanical floor passing, and the branch ready. Verify:
  `scripts/pregate-verify.sh gate2 pin-model-revisions` prints all checks passed
  and its output is recorded in the handoff. The green CI run is the gate's
  prerequisite rather than this task's evidence, so the request waits for the
  user's push and their report of the run.
