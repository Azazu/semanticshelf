# Handoff — stretch-reembedding-tooling

**Updated:** 2026-09-30 · claude
**State:** awaiting-gate-2
**Branch:** change/stretch-reembedding-tooling

## Done this session

- Branch `change/stretch-reembedding-tooling` created off `main`, which carries
  changes 0–20 archived, including `pin-model-revisions` and ADR-007.
- Change scaffolded with `openspec new change` (schema `spec-driven`).
- **Roadmap row 21 added.** This wish had no row: §9 of the requirements has
  listed "re-embedding tooling" since change 0, and `openspec/ROADMAP.md` never
  carried it. The two documents disagreed, which surfaced when the user asked
  what work was left.

## Why now

ADR-007 names this the repair for something it could not fix: vectors stored
before revisions were pinned have provenance nobody can reconstruct, and the
only way to make a corpus one model's again is to re-embed it. The project now
references tooling it does not have.

## What is already here, and what is missing

- `semanticshelf index missing [--model KEY]` queues the work stored assets have
  no vector for and carries it out. That is the **filling** half, and it exists.
- `POST /assets/{id}/reindex` re-runs one asset.
- The queue is at-least-once with leases and an idempotent upsert (ADR-003), so
  an interrupted run is already a solved problem in the layer below.
- What is missing is the **retirement** half: moving a corpus from one key to
  another and taking the old key out of service, without a window in which
  searches answer from a half-filled index.

## Questions the proposal has to answer

- **What "without downtime" means here.** Two keys coexist while the new one
  fills, and search keeps answering from the old one until the new is complete —
  so the command needs a definition of complete, and the service needs to know
  which key answers while both exist.
- **How completeness is established** before anything is deleted. Every asset
  with a vector under the old key has one under the new, counted in one place at
  one moment, or the deletion is refused.
- **What an interrupted run leaves.** Probably nothing new: the queue is
  at-least-once and the upsert is idempotent, so a re-run should be a no-op for
  what finished. That needs stating rather than assuming.
- **Whether the old key is deleted at all, or only disabled.** Deleting
  embeddings is irreversible; disabling a key is not. These are different
  promises and the requirements say "retires", which is ambiguous.
- **Risk tier.** `high`: deletion of embeddings is on this project's own trigger
  list, and so is a migration if the model allowlist has to change.

## What the proposal decided

The five questions the handoff opened with are answered, and one of them changed
the shape of the change.

- **§9's command and ADR-007's repair are not the same operation.** §9 wants two
  different keys; ADR-007 wants one key rebuilt because its weights changed.
  Underneath they differ by one predicate, so there is **one engine with two
  subcommands**: `models migrate <old> <new>` and `models reembed <key>`. Built
  only as §9 wrote it, the command would have had nothing to run against — the
  allowlist holds two keys of different spaces, and migrating between them is
  meaningless. `reembed` is the half this repository can exercise end to end.
- **"Without downtime" needs nothing built.** Which key answers a search is the
  request's own `model`, defaulting to a constant in `app/domain.py` — not a
  setting and not a database row. A second key can fill while the first keeps
  answering, and switching is a separate deliberate act.
- **Both subcommands report and change nothing without `--apply`**, following
  `storage prune`. The second reason is this machine: the work is hours of CPU,
  and the report answers "can I afford this now" from one query with no model
  loaded.
- **Completeness is counted inside the deleting statement**, not before it.
  Checked earlier and acted on later it is a race, and an upload in between
  would leave an asset whose old vector is gone and whose new one never existed.
- **`--retire` is separate from `--apply`.** Filling is additive, deleting is
  not, and one flag covering both would make the safe half carry the dangerous
  half's weight.
- **Retiring is not disabling.** The command deletes vectors and touches neither
  the configuration, the constant, nor the schema — it says in its report that a
  key left enabled will be queued for on the next upload.
- **Risk-Tier: high** — deletion of embeddings, and running models over a whole
  corpus.

## Gate 1 round 1: four findings, all fixed

Every one of them was a hole in the plan rather than a wording problem, and two
of them contradicted claims the proposal made in so many words.

**1. A statement snapshot is not serialisation (major).** Coverage tested inside
the deleting statement stops a race against the queue, and does nothing about
two retirements in opposite directions: A→B and B→A can each see themselves
covered, delete disjoint rows and both commit, leaving an asset with neither
vector. The retirement now holds the queue's own per-model advisory lock for
**both** keys, in an order sorted by key name so it does not depend on which is
being retired, across the test and the delete. Reusing the queue's lock means a
fill of either key cannot overlap a retirement either.

The reviewer also corrected the growth example, which was wrong: an asset
uploaded mid-run has a vector under *neither* key, so it is outside the coverage
predicate and cannot make the count refuse. The case that does refuse is an
asset that gains a vector under the key being **retired**, and the test says that
now.

**2. The runner switch was never mentioned (major).** `indexing-jobs` already
requires that under a configuration with a runner of its own, nothing that
creates work executes it — `index missing` asks `carries_out_work` for exactly
that reason. The plan had both commands queueing *and* carrying out, with no
word about the other configuration. Both now enqueue and execute nothing there,
say which configuration decided it, and refuse any step that needs the work
done.

**3. A re-run did not finish an interrupted one (major).** The proposal claimed
the queue's at-least-once guarantee covered it. It does not: the fill queues only
missing work — passing over assets whose work is already waiting — and drains
only what it just queued, so after a crash a re-run queues nothing and drains
nothing where no separate runner exists. The engine now carries out the
outstanding work of its own selection too, without queueing it twice, and reports
three outcomes apart: queued now, already waiting and carried out, and
untouchable — a live claim, or work that failed terminally, which only an
explicit reset may run again.

**4. The repair had no checkpoint precondition (major).** `reembed` recomputes
with the configured checkpoint, but the registry caches an embedder per process
and a queued job carries a key, not a revision — so a worker or API process
started before the setting changed can finish outstanding work with the old
weights, or overwrite a repaired vector afterwards. ADR-007 already established
that nothing in the store can see this. Design decision 7 states the order
(change the setting, restart every writer, then repair), enforces the observable
part (the repair is refused while work for that key is outstanding), and names
the limit (while a key holds vectors from two checkpoints, its scores are
comparable only within each group). It says which of those is a guarantee and
which is a precondition.

**Confirmation 1 confirmed findings 1 and 2 and returned 3 and 4 — as one
problem.** My answer to 4 broke my answer to 3: decision 7 refused a repair while
*any* work for the key was outstanding, and an interrupted repair leaves exactly
that, so its own re-run would have refused and the recovery decision 6 exists
for would never have happened.

The cases are separated now, and the separation rests on a mechanism that was
already there. **A live claim refuses**: another runner is writing that key right
now and nothing can say which checkpoint it holds. **Pending work and expired
claims do not refuse** — they are what an interrupted run leaves — because a
lease is a token: a finish lands only `WHERE lease_expires_at = <the value the
claim wrote>`, so a runner that wakes after its lease expired, including one
still holding the previous checkpoint, matches nothing and rolls back. That is
ADR-003's mechanism; what is new is leaning on it deliberately and testing that
reliance with two distinguishable checkpoints.

A fifth state joins the report: work whose **retry is not yet due**. It cannot be
run now, and a run that counted it as done would claim a rebuilt corpus it has
not rebuilt.

Tasks grew from 16 to 20: the outstanding-work query now distinguishes five
states, and the interrupted-repair test — abandon a claim, let it expire, repair
with a second fake checkpoint, then watch the stale runner's finish fail to land
— is its own.

## Gate 2 round 1: four findings, all fixed

**1. Recovery drained the key's whole backlog, not the selection's (major).**
`outstanding` had no vector predicate, so a migration A→B executed unrelated B
work on assets with no A vector — expensive work its own plan never counted. It
now takes the same selection predicates the queueing statement uses, and the run
asks it twice on purpose: the **live-claim preflight is about the key**, because
any runner writing it may hold other weights whichever assets it is on, while
what this run may **carry out is about its selection**.

**2. Completion ignored failures produced by the run (major).** A job that
exhausts its attempts lands in `work.failed`, not `work.queued`, and
`skipped_failed` only holds what failed *before* the run — so the report printed
"failed: 1" and "complete: the key owes nothing" together. The regression queues
the work with its retries already spent, because a missing file alone is a
retryable failure and "waiting" is not "gave up".

**3. A refused deletion announced itself as a retirement (major).** When
coverage changed between the service's reading and the DELETE, the statement
correctly removed nothing and the service reported `retired: 0 vector(s)`. The
window is real — claiming, finishing and upserting take none of these locks — and
the service now recounts and says the corpus changed. The regression makes that
deterministic by having the reading answer "covered" once while the corpus is
not, which is exactly what the interval looks like from the service's side.

**4. The stale-runner verification did not verify (major).** It called
`mark_done` rather than driving a real result through `indexing.finish`, and it
compared the repaired vectors with themselves. It now finishes the way any
runner does — one transaction that marks the work done and writes its vector —
and asserts the surviving vector equals what the **new** checkpoint answers,
computed independently. Two demonstrations the table was missing are in it: the
lease token, and the retirement that needs its word.

## Gate 2 confirmation 1: two confirmed, two returned

**Finding 1 came back because I fixed the execution and forgot the report.**
`describe_plan` still asked about the whole key, so an empty migration with one
unrelated pending job promised "already waiting: 1" and then carried over
nothing — a dry run that overstates the work is the opposite of what a dry run
is for. It now asks the same two questions the run does and says which is which:
the selection's own outstanding work on its lines, and live claims **anywhere**
on the key on a line that says so, because a repair refuses on any of them
whichever assets they cover. Three shapes of unrelated work are covered —
pending, expired and delayed.

**Finding 3 came back because my fix still trusted a count taken before the
delete.** `removed == 0 and held` skipped the recount when the key held nothing
at the start, so a retirement over an initially empty key announced
`retired: 0 vector(s) ... deleted` even where the statement had refused. The
count is gone: a zero removal is always explained by a fresh reading, which
separates "the corpus changed under this run" from "there was nothing to
retire".

And the regression no longer substitutes the coverage query's answer. A real
second session commits an old-only vector on the first call of the real query —
which is what that interval is — and it runs for a key that starts empty and one
that starts with vectors. Getting it to fail first took a correction of my own
setup: the intruder had kept its replacement vector, which made the corpus
covered again and the delete rightly proceeded.

## Demonstrated failing inputs (high tier, task 5.1)

Each guard removed on its own, the covering test run, the file restored.

| check | file | test | with the guard removed |
|---|---|---|---|
| an unknown key is refused | `app/cli.py` | `-k schema_does_not_allow` | FAILED |
| a key this build does not run is refused | `app/cli.py` | `-k build_does_not_run` | FAILED |
| a key cannot replace itself | `app/cli.py` | `-k replace_itself` | FAILED |
| a repair refuses a live claim | `app/services/indexing.py` | `-k refuses_to_begin` | FAILED |
| a run carries out what was left outstanding | `app/services/indexing.py` | `-k interrupted_one_left` | FAILED |
| a retirement refuses while the queue owes work | `app/services/indexing.py` | `-k owes_work` | FAILED |
| a retirement refuses an incomplete replacement | `app/services/indexing.py` | `-k incomplete_replacement` | FAILED |
| coverage is tested inside the deleting statement | `app/repositories/embeddings.py` | `-k statement_deletes_nothing` | FAILED |
| two retirements cannot undo each other | `app/services/indexing.py` | `-k waits_while_another` | FAILED |
| a stale runner's finish cannot land | `app/services/indexing.py` | `-k wakes_after` | FAILED |
| a retirement needs the word | `app/cli.py` | `-k without_retire` | FAILED |
| a run recovers its own selection only | `app/repositories/jobs.py` | `-k unrelated_backlog` | FAILED |
| a failure during the run is not completion | `app/services/indexing.py` | `-k fails_terminally` | FAILED |
| a zero removal is explained by a fresh reading | `app/services/indexing.py` | `-k written_after_the_reading` | FAILED |
| a plan counts its own selection | `app/services/indexing.py` | `-k counts_only_its_own` | FAILED |

**Three of these read `passed` first, and each time the run was wrong rather
than the guard.** They are worth recording because two of them are mistakes
anyone repeating this work would make.

1. `__pycache__` was cleared only at the top of `app/`, and the modules under
   test live in subpackages — the plants ran against stale bytecode.
2. The condition inside the deleting statement had **no test that reached it**.
   The service refuses first, so its own test never gets that far, and the
   statement is where the guarantee lives. A repository-level test was added.
3. The two-retirement test was **non-deterministic**: it is a race, and its
   outcome depends on the interleaving — it failed standalone and passed in a
   batch. A demonstration whose result depends on the scheduler demonstrates
   nothing. It was replaced by a deterministic test of the serialisation: one
   session holds both locks open, a retirement that wants them must wait and
   hits its timeout, and it succeeds once the holder commits. The race test is
   kept as a sanity check beside it.

## What CI runs, run locally (task 5.3)

| command | result |
|---|---|
| `FORCE_COLOR=1 CI=true make check` | **green** — 858 passed |
| `openspec validate --all --strict` | **green** — 17 passed |
| `sh -n scripts/*.sh` | **green** — 7 files |
| `scripts/gate_run_test.sh` | **green** — 77 passed |
| `scripts/workflow_verify_test.sh` | **green** — 23 passed |
| `FORCE_COLOR=1 CI=true make test-integration` | **green** — 346 passed (was 296) |
| `make audit` | **green** — no known vulnerabilities in 97 packages |
| `make image` | **green** — `semanticshelf:runtime` 1.79 GB, unchanged |

Both commands printed in the how-to were run in that form, and the output shown
there is the output they gave: an earlier draft printed `vectors to compute: 500`
over a store that holds none, which is a number no reader could have reproduced.

## The mechanical floor for Gate 2 (task 5.4)

```console
$ scripts/pregate-verify.sh gate2 stretch-reembedding-tooling
[OK]   git diff --check clean
[OK]   openspec validate stretch-reembedding-tooling --strict
[OK]   risk tier declared: high
[OK]   proposal.md has a Non-goals section
[OK]   tasks.md has 20 task(s)
[OK]   every task checked
[OK]   checked-task referenced paths exist
[OK]   markdown links resolve (13 changed .md files)
[OK]   make check green
pregate-verify: gate2 stretch-reembedding-tooling — all checks passed (0 warning(s))
```

## Next step

**Gate 1 is passed** — confirmation 2 on `c89e9a3` confirms all four findings.

The user pushes `change/stretch-reembedding-tooling` and reports the CI run;
then `/gate-review stretch-reembedding-tooling 2` — Gate 2 on the code diff.

## Blockers

None.
