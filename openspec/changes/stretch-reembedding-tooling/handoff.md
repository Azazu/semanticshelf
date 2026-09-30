# Handoff — stretch-reembedding-tooling

**Updated:** 2026-09-30 · claude
**State:** awaiting-gate-1
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

## Next step

`/gate-review stretch-reembedding-tooling 1` — Gate 1 on the artifacts.
`scripts/pregate-verify.sh gate1 stretch-reembedding-tooling` passes (16 tasks,
tier declared, applicability table present, links resolve).

## Blockers

None.
