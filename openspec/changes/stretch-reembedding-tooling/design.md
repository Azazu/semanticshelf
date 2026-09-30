# Design — stretch-reembedding-tooling

## Context

See `proposal.md` — Why. Four facts from the current source shape everything
below.

- **The filling half exists.** `index missing --model KEY` selects assets with
  no vector for a key, queues work and carries it out (`app/cli.py`,
  `_run_backfill`). What a rebuild needs is the same machinery with the
  selection inverted.
- **The queue already survives interruption.** At-least-once with leases and an
  idempotent upsert (ADR-003): a killed run leaves work that another run picks
  up, and a vector written twice is written once.
- **Which key answers is the request's own `model`**, defaulting to a constant
  in `app/domain.py` — not a setting, not a database row. So a corpus can grow a
  second key without any search changing what it answers, and "without downtime"
  costs nothing to arrange.
- **A destructive command in this repository reports first.** `storage prune`
  does nothing at all without `--apply`. That is the precedent, and this change
  follows it rather than inventing a second convention.

## Goals / Non-Goals

**Goals**

- One engine, so a rebuild and a migration cannot drift apart.
- A number an operator can act on *before* the machine starts working.
- A deletion that cannot happen while anything still depends on what is deleted.

**Non-Goals** (beyond the proposal's)

- No progress record beside the queue.
- No opinion about which key *should* answer; that is a code change elsewhere.

## Applicability (high tier)

| Question | This change |
|---|---|
| Deletion and expiry | The only deletion is a retirement, and it is guarded twice: by a completeness count taken in the same statement that authorises it, and by an explicit word on the command line. Nothing expires; a key's vectors live until an operator retires them. |
| Crash around an external effect | A crash leaves queued or leased work and nothing half-written, because a vector and its finished work are one act (`indexing-jobs`). What it does **not** leave is a run that the next one finishes by itself: the existing fill queues only what is missing and drains only what it just queued, so after a crash a re-run queues nothing and drains nothing where no separate runner exists. The engine therefore carries out the outstanding work of its own selection as well as the work it queued (decision 6). A crash between the coverage test and the delete leaves the corpus as it was: they are one statement, and an interrupted command has not run it. |
| Concurrent writers | Three writers to answer for. **Two fills** cannot double-queue: the queue already takes a per-model advisory lock before it selects. **A fill and an upload**: an asset uploaded during a fill has no vector under either key, so it is outside the coverage predicate and cannot make the count refuse — what it does mean is that the corpus is not covered afterwards either, and the operator runs the fill again. The case that *does* refuse is an asset that gains a vector under the key being retired during the run, which is why the count lives inside the deleting statement. **Two retirements** are the dangerous pair, and a statement snapshot does not serialise them: A→B and B→A can each see themselves covered, delete disjoint rows and leave an asset with neither vector. A retirement therefore holds the queue's per-model lock for **both** keys, in a fixed order that does not depend on which is being retired, for the whole of the test and the delete (decision 3). |
| Empty, zero and null inputs | A corpus with no assets is complete by definition, and retiring a key of no vectors deletes nothing and says so rather than reporting success over an empty set. A key the schema does not allow is refused before anything is queued; so is a rebuild of a key this build does not run, because its work would be queued and never carried out by anyone. Zero outstanding work and zero uncovered assets are different facts and are reported apart. |
| Idempotent retries | Running the fill twice queues nothing the first run has outstanding and carries out what it left, which is the point of decision 6. Running the retirement twice deletes nothing the second time: the key has no vectors left, the coverage test is trivially satisfied, and the run reports that it removed none. |
| Authorization boundary | n/a — an operator's command, not an endpoint. The API gains nothing. |
| Money and rounding | n/a. |

## Decisions

### 1. Two subcommands, one engine

`models migrate <old> <new>` and `models reembed <key>` differ in one predicate:
which assets need work. Migrate selects assets having a vector under `old`;
reembed selects assets having a vector under `key`. Everything after that — the
queue, the runner, the counting, the reporting — is shared.

They are separate subcommands rather than one with a flag because they are
different sentences: one replaces a key, the other rebuilds it, and an operator
reaching for the wrong one should be told by the shape of the command rather
than by its arguments. `migrate <key> <key>` is refused for the same reason.

*What this guarantees:* the repair ADR-007 names can be run against this
repository's own corpus today, and the upgrade §9 asked for works the moment a
second key of the same kind exists. *What it does not:* it does not make an
upgrade meaningful between the two keys installed now, which are different
spaces.

### 2. Report first, act on `--apply`

Both subcommands, without `--apply`, compute nothing and change nothing. They
print how many assets need work, how many vectors that is, and what a retirement
would do.

This is `storage prune`'s convention, and there is a second reason for it here:
the work is hours of CPU on a laptop. A command that starts a three-hour job
because its name sounded additive is a bad command. The count is the answer to
"can I afford this right now", and it is cheap to get — one query, no model
loaded.

*What this guarantees:* nothing expensive and nothing irreversible happens
without a word that means it. *What it does not:* the report is a moment's
truth, and a corpus that grows between the report and the run is bigger than the
report said. The completeness count before a deletion is taken again, for that
reason.

### 3. Coverage is tested inside the delete, under both keys' locks

"Every asset with a vector under `old` has one under `new`" is tested **in the
delete's own statement**. Tested earlier and acted on later it is a race: work
finishing in between leaves an asset the new key cannot answer for, and its old
vector is gone.

**A statement snapshot is not serialisation, though**, and that is the sharper
problem. Two retirements in opposite directions — A in favour of B, B in favour
of A — can each see themselves fully covered, delete disjoint rows, and both
commit. The asset is then left with no vector at all, from two operations each
of which was individually safe.

So a retirement takes the queue's own per-model advisory lock for **both** keys,
in a fixed order — sorted by key name, so it does not depend on which key is
being retired — and holds them across the coverage test and the delete. The
fixed order is what makes two opposite retirements queue up instead of
deadlocking, and reusing the queue's lock rather than inventing one means a fill
of either key cannot overlap a retirement either.

**And coverage is not enough by itself.** A count is about vectors; work in the
queue is about vectors that do not exist yet. A retirement is therefore refused
while any work for the replacing key is waiting, running or failed — a corpus
the queue is still changing is not a corpus anyone can vouch for.

*What this guarantees:* no window, and no pair of retirements that undo each
other. *What it does not:* it says nothing about whether the new key's vectors
are any *good*; coverage is a count, not a measurement. That distinction is
ADR-006's subject and is not relitigated here.

### 4. Retirement is a word, not a consequence

`--retire` is separate from `--apply`. `--apply` alone fills; `--apply --retire`
fills and then deletes. A fill is additive and a deletion is not, and one flag
covering both would make the safe half carry the dangerous half's weight.

*What this guarantees:* an operator who wanted only to fill cannot delete by
forgetting something. *What it does not:* it does not protect against an
operator who types both and means one; nothing can, and the refusal on
incompleteness is the backstop.

### 5. Retiring a key is not disabling it

The command deletes vectors. It does not touch `EMBEDDING_MODELS`, the schema's
CHECK, or `ENABLED_MODELS` — those are a repository constant, a migration and
configuration, in that order, and each is a deliberate act with its own review.
A deployment that retires a key and leaves it enabled will queue work for it on
the next upload; the command says so in its report rather than deciding for the
operator.

*Alternative considered:* also removing the key from the enabled set. Rejected:
a command that edits configuration is a command that surprises the next
deployment, and the setting is not the command's to own.

### 6. A run finishes what the last one left

The existing fill queues only the work a key is missing and drains only the work
it just queued. Those two together have a hole: after a crash, the next run
queues nothing — the assets already have work waiting, so the selection passes
over them — and drains nothing, because it queued nothing. Where a separate
runner exists it will pick the work up; where the queue is carried by the
command itself, nobody does.

The engine therefore drains **the outstanding work of its own selection** beside
the work it queued, without queueing it again. Three outcomes are reported
apart, because they need different acts: queued by this run, already waiting and
carried out by this run, and untouchable — a claim another runner still holds,
or work that failed terminally, which the existing rule says only an explicit
reset may run again. A rebuild does not get to suspend that rule.

*What this guarantees:* a second run of the same command finishes the first.
*What it does not:* it does not make the command a worker. It touches only its
own selection, and it never breaks another runner's live claim.

### 7. Repairing a key is an operation with a precondition, not a spell

`reembed` recomputes a key's vectors with the checkpoint this build is
configured to read. That is only a repair if nothing else is writing that key
with the checkpoint it used to read — and a process that loaded the model
before the configuration changed keeps it: the registry caches an embedder per
process for the life of that process, and a queued job carries a key, never a
revision. So an API process or a worker started before the change can finish
outstanding work with the old weights, or overwrite a repaired vector
afterwards, and the corpus is mixed again with nothing to show for the hours.

Nothing in the store can detect that — ADR-007 established exactly this, and the
provenance table that would detect it was designed and refused there. What this
change does instead is state the precondition and enforce the part of it that is
observable:

- **Stated:** every process that writes this key must already be running the new
  configuration. In practice: change the setting, restart the writers, then
  repair. The documentation gives that order and says why.
- **Enforced:** the repair is refused while any work for that key is waiting,
  running or failed. Outstanding work is the observable shadow of a writer that
  may still be holding the old weights, and refusing is cheap where guessing is
  not.
- **Limited:** while a key holds vectors from two checkpoints, its scores are
  comparable only within each group, and the search that ranks them cannot tell
  them apart. That is the state a repair exists to leave, and it is named in the
  how-to rather than left for someone to deduce from a bad result.

*What this guarantees:* the window in which an old-weights writer can undo the
repair is the window in which an operator ignored the documented order. *What it
does not:* it is a precondition, not a lock. A writer started with the old
configuration and no outstanding work is invisible to this command, and only
restarting it fixes that.

## Risks / Trade-offs

- **Hours of CPU** → that is the nature of the work, and the report exists so it
  is chosen rather than discovered. Nothing schedules it.
- **An irreversible deletion** → guarded by a count in the deleting statement
  and by an explicit word, and refused entirely when anything would be left
  uncovered.
- **Two subcommands to keep in step** → one engine underneath, and the tests
  drive both through it.
- **A repair another process can undo** → a stated order of operations, a
  refusal while work is outstanding, and a named limit on what a mixed key
  means. Decision 7 says plainly which of those is a guarantee and which is a
  precondition.
- **`migrate` has no meaningful pair of keys today** → stated in the proposal.
  `reembed` does, and it is the one this repository can exercise end to end,
  which is why both exist rather than only the one §9 named.

## Migration Plan

No schema change and no data migration. The command is new; nothing that exists
behaves differently.

## Open Questions

None that change the specs, the approach or the tasks.
