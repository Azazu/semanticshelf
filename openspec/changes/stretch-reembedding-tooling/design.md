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
| Crash around an external effect | A crash during the fill leaves queued or leased work, which the existing runner picks up — nothing new is needed and nothing is half-written, because a vector and its finished work are one act (`indexing-jobs`). A crash between the completeness count and the delete leaves the corpus as it was: the delete is one statement, and an interrupted command has not run it. |
| Concurrent writers | An upload during the fill adds an asset with no vector under either key; the completeness count at the moment of the delete sees it and refuses. Two runs of the fill at once add no duplicate work — an asset with work waiting or running is passed over, which is the existing rule. |
| Empty, zero and null inputs | A corpus with no assets is complete by definition, and retiring a key of no vectors deletes nothing and says so rather than reporting success over an empty set. A key the schema does not allow is refused before anything is queued; so is a rebuild of a key this build cannot run, because the work would be queued and never carried out. |
| Idempotent retries | Running the fill twice queues nothing the first run has outstanding. Running the retirement twice deletes nothing the second time, because the key has no vectors left and the completeness count is trivially satisfied — the second run reports that it removed none. |
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

### 3. Completeness is a count in the same statement that deletes

"Every asset with a vector under `old` has one under `new`" is checked **in the
delete's own statement**, not before it. Checked earlier and acted on later, it
is a race: an upload between the two leaves an asset the new key cannot answer
for, and its old vector is gone.

So the deletion is conditional by construction — it removes the old key's
vectors only for assets that have a new one, and refuses as a whole if any asset
would be left uncovered.

*What this guarantees:* no window. *What it does not:* it says nothing about
whether the new key's vectors are any *good*; completeness is a count, not a
measurement. That distinction is ADR-006's subject and is not relitigated here.

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

## Risks / Trade-offs

- **Hours of CPU** → that is the nature of the work, and the report exists so it
  is chosen rather than discovered. Nothing schedules it.
- **An irreversible deletion** → guarded by a count in the deleting statement
  and by an explicit word, and refused entirely when anything would be left
  uncovered.
- **Two subcommands to keep in step** → one engine underneath, and the tests
  drive both through it.
- **`migrate` has no meaningful pair of keys today** → stated in the proposal.
  `reembed` does, and it is the one this repository can exercise end to end,
  which is why both exist rather than only the one §9 named.

## Migration Plan

No schema change and no data migration. The command is new; nothing that exists
behaves differently.

## Open Questions

None that change the specs, the approach or the tasks.
