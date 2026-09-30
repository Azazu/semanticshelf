# Tasks — stretch-reembedding-tooling

## 1. What the store can be asked

- [x] 1.1 The selection a rebuild needs: the assets that **already have** a
  vector under a named key, beside the existing "assets that have none". Verify:
  integration tests that it returns exactly those assets, that it is empty for a
  key nothing is stored under, and that it does not depend on any other key's
  vectors.
- [x] 1.2 The coverage count: how many assets have a vector under one key and
  none under another, **in one statement**, loading no model. Verify:
  integration tests for zero (the replacement covers everything), for a positive
  count naming how many, for an empty corpus, and for the pair given in the
  other order — the count is not symmetric and the test says so.
- [x] 1.3 The outstanding-work query: for a key and a selection, the work that
  is waiting, the work whose retry is **not yet due**, the work a **live** claim
  holds, the work whose claim has **expired**, and the work that failed
  terminally — five states told apart, because the commands act differently on
  each. Loads no model. Verify: integration tests for each state and for none of
  them, and one that a live claim and an expired one give different answers,
  since the repair refuses on the first and carries out the second.

## 2. The engine and its two sentences

- [x] 2.1 One engine over the existing queue: given a selection, queue the work,
  and carry out **both what it queued and what its selection already had
  outstanding** (design decision 6), with the leases, the at-least-once
  guarantee and the idempotent upsert untouched (ADR-003). It queues nothing
  twice, breaks no live claim, and does not run work that failed. Verify:
  integration tests — a rebuild replaces a vector rather than adding a row; a
  run killed after queueing and before draining is finished by the next run,
  which queues nothing and drains what was waiting; work under a live claim is
  left alone and reported as held; work that failed terminally is neither queued
  nor run and is reported as failed; the three outcomes are reported apart.
- [x] 2.2 The runner switch, unchanged (design decision 6 and the
  `indexing-jobs` delta): under a configuration where a runner of its own
  executes the queue, both commands enqueue and execute nothing, say which
  configuration decided it, and refuse any step that needs the work to be done.
  Verify: integration tests of both commands under both runner configurations,
  asserting that nothing was executed under the second and that the reason is
  named — the same `carries_out_work` the other commands ask.
- [x] 2.3 `semanticshelf models reembed <key>`: recompute every vector stored
  under one key. Verify: an integration test end to end on the fake embedder,
  asserting every vector changed and the row count did not; a test that a key
  this build does not run is refused before anything is queued; a test that a
  key the schema does not allow is refused with its name; and — design decision
  7 — a test that the repair is **refused while another runner holds a live
  claim** on that key, and a test that it is **not** refused when the key's
  outstanding work is merely pending or held by an expired claim, because that
  is what an interrupted repair leaves and finishing it is the point.
- [x] 2.4 `semanticshelf models migrate <old-key> <new-key>`: fill the new key
  for every asset holding a vector under the old. Verify: integration tests that
  only those assets are queued, that `migrate <key> <key>` is refused, and that
  an unknown key on either side is refused before anything is queued.
- [x] 2.6 A repair survives its own interruption, and a stale writer cannot undo
  it (design decision 7, and the reason findings 3 and 4 were one problem).
  Verify: an integration test with **two distinguishable fake checkpoints** —
  a runner claims work for the key and is abandoned holding it; its lease
  expires; the repair runs to completion with the second checkpoint; the
  abandoned runner then tries to finish the work it claimed and its result does
  not land, because a finish matches only the lease expiry its own claim wrote.
  Every vector under the key afterwards comes from the second checkpoint, and
  the test asserts that by value rather than by count. Plus a test of the
  supported order — configuration changed, writers restarted, repair run — and
  one that work whose retry is not yet due is reported as such and the run does
  not claim the corpus is rebuilt.

- [x] 2.5 Both report and change nothing without `--apply` (design decision 2):
  how many assets need work, how many vectors that is, and what a retirement
  would do. Verify: integration tests that without `--apply` the queue is empty
  afterwards and no vector changed, and that the report's numbers match what a
  subsequent `--apply` run actually does.

## 3. Retiring a key

- [x] 3.1 `--retire`, separate from `--apply` (design decisions 3 and 4): delete
  the old key's vectors **in a statement whose own condition is that every asset
  holding one has a vector under the new key**, refuse as a whole when any asset
  would be left uncovered, naming how many, and refuse while the queue owes
  anything for the replacing key. Verify: integration tests — a complete
  replacement retires and leaves assets, files and other keys untouched; an
  incomplete one deletes nothing and names the number; one where coverage holds
  but work is still waiting is refused and says so; **an asset given a vector
  under the retiring key after the fill ended** is refused on the count taken
  inside the delete; `--apply` without `--retire` deletes nothing whatever the
  state.
- [x] 3.2 Two retirements cannot undo each other (design decision 3): the
  retirement holds the queue's per-model advisory lock for **both** keys, in an
  order sorted by key name so it does not depend on which is being retired, for
  the whole of the coverage test and the delete. Verify: a two-session
  integration test — A→B and B→A attempted at once over an asset covered by
  both — asserting that they serialise, that the second refuses, and that no
  asset is left without a vector under either key; and a test that a fill of
  either key cannot overlap a retirement of it.
- [x] 3.3 Retiring is not disabling (design decision 5): the command touches
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
  form; `docs/how-to/models.md` gains a section on replacing a model **and one
  on repairing a key after its checkpoint moved**, with the order of operations
  design decision 7 requires — change the setting, restart every writer, then
  repair — why that order and not another, and what a key holding vectors from
  two checkpoints means for a search until the repair finishes. Verify: both re-read whole after
  the last edit; every command printed was run in that form.
- [ ] 4.4 Reconcile the plan: `openspec/ROADMAP.md` row 21 and
  `docs/explanation/requirements.md` §9, which has asked for this since change 0
  and describes only the migrate half. Verify: both re-read whole; no document
  describes tooling that does not exist, and none omits the half that does.

## 5. Closing the change

- [ ] 5.1 A demonstrated failing input for every new or changed check (high
  tier): the refusal of an unknown key, of a key this build does not run, of
  `migrate <key> <key>`, of a retirement while incomplete, of a retirement while
  the queue owes work, of a retirement without the word, of a repair while a
  live claim is held, the coverage condition inside the delete, the two-key
  lock, the draining of a selection's outstanding work, and the lease token that
  voids a stale runner's late finish.
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
