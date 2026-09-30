# ADR-008: a corpus is rebuilt by one engine, and a key is retired only under both locks

**Date:** 2026-09-30
**Status:** accepted
**Related:** ADR-003 (the queue this rests on: leases, at-least-once, the idempotent upsert); ADR-007 (the repair this provides, and why nothing can detect the problem it repairs); ADR-001 (an embedding's identity is its asset and its model key); authored by the OpenSpec change `stretch-reembedding-tooling`

## Context

§9 of the requirements has asked for `models migrate <old-key> <new-key>` since
change 0 — "for model upgrades without downtime" — and the plan never carried a
row for it. ADR-007 then made it load-bearing: it names re-embedding as the only
repair for vectors stored before checkpoint revisions were pinned, whose
provenance nobody can reconstruct.

Half of it already existed. `index missing` queues the work a key has none of
and carries it out; the queue is at-least-once with leases and an idempotent
upsert; `POST /assets/{id}/reindex` re-runs one asset. What was missing was
everything after filling.

And the two callers wanted different operations. §9 wants **two keys**; ADR-007
wants **one key rebuilt** because its weights moved. Built only as §9 wrote it,
the command would have had nothing to run against: today's allowlist holds two
keys of different spaces, and migrating between them is meaningless.

## Decision

**One engine, two subcommands.** `models reembed <key>` recomputes a key's
vectors; `models migrate <old> <new>` fills the new key for the assets the old
one answers for. They differ in one predicate and share everything after it, so
they cannot drift apart. `migrate <key> <key>` is refused and says which command
means that.

**A run carries out what an earlier run left.** The existing fill queues only
missing work — passing over assets whose work is already waiting — and drains
only what it just queued. After a crash that is nothing and nothing: a re-run
reports success over a corpus it never touched. The engine therefore drains its
selection's outstanding work as well, without queueing it again, and reports
five states apart: queued now, carried over, retried-but-not-yet-due, held by
another runner, and failed terminally, which only an explicit reset may run
again.

**Report first; `--apply` to act.** Both subcommands compute nothing and change
nothing without it, as `storage prune` does not delete without `--apply`. The
second reason is the machine: the work is hours of CPU, and the count is the
answer to "can I afford this now" from three statements with no model loaded.

**Retirement is a separate word from applying.** `--apply` fills; `--apply
--retire` fills and then deletes. Filling is additive and deleting is not, and
one flag covering both would make the safe half carry the dangerous half's
weight.

**Coverage is tested inside the deleting statement, under both keys' locks.**
The condition — no asset holds a vector under the retiring key without one under
the replacing key — is part of the DELETE, because tested earlier and acted on
later it is a race. And because a statement snapshot is not serialisation: two
retirements in opposite directions can each see themselves covered, delete
disjoint rows and both commit, leaving an asset with neither vector. So a
retirement takes the queue's own per-model advisory lock for **both** keys, in
an order sorted by key name — the fixed order is what makes two opposite
retirements queue up instead of deadlocking — and holds them across the test and
the delete. Reusing the queue's lock means a fill of either key cannot overlap a
retirement either.

**A retirement is also refused while the queue owes anything** for the replacing
key: a count taken while work is outstanding describes a corpus that is still
changing.

**Retiring is not disabling.** The command deletes vectors. It touches neither
`ENABLED_MODELS`, which is configuration, nor the schema's allowlist, which is a
migration, nor the registry's constant. It says in its report that a key left
enabled will be queued for on the next upload.

**A repair refuses a live claim and nothing else.** `reembed` recomputes with
the configured checkpoint, and a process that loaded the model earlier keeps it
— the registry caches an embedder per process, and a queued job carries a key,
not a revision. A live claim is a writer working now whose weights nothing can
see, so a repair does not begin. Pending work and expired claims are **not**
grounds to refuse: they are what an interrupted repair leaves, and refusing on
them would make a repair unable to finish itself. That is safe because a lease
is a token — a finish lands only where the lease expiry its own claim wrote is
still the row's — so a runner that wakes late, including one still holding the
previous checkpoint, rolls back rather than overwriting a repaired vector.

## Alternatives considered

**Building only `migrate`, as §9 wrote it.** Rejected: no meaningful pair of
keys exists in the allowlist today, so it could never have been run end to end —
only against an invented key in tests.

**Refusing a repair while any work is outstanding.** This was the first draft's
answer to the stale-writer problem, and it contradicted the recovery in the same
document: an interrupted repair leaves outstanding work, so its own re-run would
have refused. Replaced by the live-claim rule above.

**A progress record beside the queue.** Rejected: the queue is the record, and a
second source of truth about what has been done is how two of them disagree.

**Removing the key from `ENABLED_MODELS` as part of retiring.** Rejected: a
command that edits configuration surprises the next deployment, and the setting
is not the command's to own.

**Automatically switching which key answers a search.** Rejected, and nothing
was needed to avoid it: which key answers is the request's own `model`,
defaulting to a constant in `app/domain.py`. A second key fills while the first
keeps answering, and the switch is a separate deliberate act — which is what
"without downtime" meant all along.

## Consequences

**The repair ADR-007 names exists**, and can be run against this repository's
own corpus. The upgrade §9 asked for works the moment a second key of the same
kind exists.

**An interrupted run is finished by the next one**, which was not true of the
tooling that existed.

**A deletion cannot leave an asset unanswerable** — not by a race with the
queue, and not by another retirement.

**What is not guaranteed:** that a writer started with the previous checkpoint
and holding no claim is not still running. Nothing in the store can see which
weights a process holds; ADR-007 established that and refused the table that
would have. The documented order — change the setting, restart every writer,
then repair — is a precondition, not a lock, and the how-to says so.

**And while a key holds vectors from two checkpoints**, its scores are
comparable only within each group and the search ranking them cannot tell them
apart. That is the state a repair passes through.

## Supersedes

No ADR clause. ADR-003's queue is used as it is, and ADR-001's identity rule is
what keeps the revision out of the `embeddings` table.
