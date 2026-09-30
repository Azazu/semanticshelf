# Tasks — stretch-reembedding-tooling

## 1. What the store can be asked

- [ ] 1.1 The selection a rebuild needs: the assets that **already have** a
  vector under a named key, beside the existing "assets that have none". Verify:
  integration tests that it returns exactly those assets, that it is empty for a
  key nothing is stored under, and that it does not depend on any other key's
  vectors.
- [ ] 1.2 The completeness count: how many assets have a vector under one key
  and none under another, **in one statement**, loading no model. Verify:
  integration tests for zero (the replacement covers everything), for a positive
  count naming how many, for an empty corpus, and for the pair given in the
  other order — the count is not symmetric and the test says so.

## 2. The engine and its two sentences

- [ ] 2.1 One engine over the existing queue: given a selection, queue the work
  and carry it out through the runner that already exists, with the leases, the
  at-least-once guarantee and the idempotent upsert untouched (ADR-003). Verify:
  an integration test that a rebuild replaces a vector rather than adding a
  second row, and one that an interrupted run finished by a second run leaves
  each asset with exactly one current vector.
- [ ] 2.2 `semanticshelf models reembed <key>`: recompute every vector stored
  under one key. Verify: an integration test end to end on the fake embedder,
  asserting every vector changed and the row count did not; a test that a key
  this build does not run is refused before anything is queued; a test that a
  key the schema does not allow is refused with its name.
- [ ] 2.3 `semanticshelf models migrate <old-key> <new-key>`: fill the new key
  for every asset holding a vector under the old. Verify: integration tests that
  only those assets are queued, that `migrate <key> <key>` is refused, and that
  an unknown key on either side is refused before anything is queued.
- [ ] 2.4 Both report and change nothing without `--apply` (design decision 2):
  how many assets need work, how many vectors that is, and what a retirement
  would do. Verify: integration tests that without `--apply` the queue is empty
  afterwards and no vector changed, and that the report's numbers match what a
  subsequent `--apply` run actually does.

## 3. Retiring a key

- [ ] 3.1 `--retire`, separate from `--apply` (design decisions 3 and 4): delete
  the old key's vectors **in a statement whose own condition is that every asset
  holding one has a vector under the new key**, and refuse as a whole when any
  asset would be left uncovered, naming how many. Verify: integration tests —
  a complete replacement retires and leaves assets, files and other keys
  untouched; an incomplete one deletes nothing and names the number; a corpus
  that grew between the fill and the retirement is refused on the later count;
  `--apply` without `--retire` deletes nothing whatever the state.
- [ ] 3.2 Retiring is not disabling (design decision 5): the command touches
  neither `ENABLED_MODELS`, nor `EMBEDDING_MODELS`, nor the schema's CHECK, and
  says in its report that a key left enabled will be queued for on the next
  upload. Verify: a test that the settings and the schema are unchanged after a
  retirement; the report's wording is asserted.

## 4. The record and the documents

- [ ] 4.1 Both deltas land as written. Verify: `openspec validate --strict`;
  each scenario of each delta has a test.
- [ ] 4.2 `docs/adr/ADR-008-reembedding-a-corpus.md`: why one engine carries two
  subcommands, why the completeness count lives inside the deleting statement,
  why retirement is a separate word from applying, and why the command does not
  touch configuration. It names ADR-003 (the queue it rests on) and ADR-007 (the
  repair it provides). Verify: the ADR index carries its row.
- [ ] 4.3 `docs/reference/commands.md` gains both subcommands in their exact
  form; `docs/how-to/models.md` gains a section on replacing a model, with the
  order of operations and what each step costs. Verify: both re-read whole after
  the last edit; every command printed was run in that form.
- [ ] 4.4 Reconcile the plan: `openspec/ROADMAP.md` row 21 and
  `docs/explanation/requirements.md` §9, which has asked for this since change 0
  and describes only the migrate half. Verify: both re-read whole; no document
  describes tooling that does not exist, and none omits the half that does.

## 5. Closing the change

- [ ] 5.1 A demonstrated failing input for every new or changed check (high
  tier): the refusal of an unknown key, of a key this build does not run, of
  `migrate <key> <key>`, of a retirement while incomplete, of a retirement
  without the word, and the completeness count's condition inside the delete.
  Verify: one table, one row per check, each a run with that one edit and the
  file restored afterwards.
- [ ] 5.2 `openspec validate stretch-reembedding-tooling --strict` passes and
  every task above is checked with its evidence.
- [ ] 5.3 Run locally everything CI runs, in CI's own form:
  `FORCE_COLOR=1 CI=true make check`, `openspec validate --all --strict`,
  `sh -n scripts/*.sh`, every `scripts/*_test.sh`,
  `FORCE_COLOR=1 CI=true make test-integration` with the database up,
  `make audit`, and `make image`. Verify: each command's result recorded in the
  handoff.
- [ ] 5.4 Hand over for the push: `handoff.md` at `awaiting-gate-2`, the
  mechanical floor passing, and the branch ready. Verify:
  `scripts/pregate-verify.sh gate2 stretch-reembedding-tooling` prints all
  checks passed and its output is recorded in the handoff. The green CI run is
  the gate's prerequisite rather than this task's evidence, so the request waits
  for the user's push and their report of the run.
