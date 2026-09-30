## ADDED Requirements

### Requirement: A corpus can be rebuilt under a key, or filled under another

An operator can already ask for the work a key is **missing**. Three more
questions need answering before a model can be replaced: give me the work a key
would need to be rebuilt from scratch, tell me whether a key is complete for
this corpus, and tell me what is still outstanding.

The service SHALL create work for every asset that **already has** a vector
under a named key, so that key's vectors are recomputed and replaced. This is
the same queue, the same per-model advisory lock, the same leases and the same
idempotent upsert as every other piece of work.

**Work that was already outstanding is part of the job, not a gap in it.** The
selection skips an asset whose work for that key is waiting, running or failed —
that is the existing rule and it stays. But a run SHALL also carry out the
outstanding work of its own selection, so that a run interrupted halfway is
finished by the next one rather than leaving work nobody drains. It SHALL NOT
queue that work a second time.

Four states are reported apart, because they need different acts from an
operator: work this run **queued**; work that was **already waiting** and this
run carried out; work whose **retry is not yet due**, which cannot be run now
and which SHALL NOT be counted as done; and work it could not touch — a claim
another runner still holds, or work that has **failed** and which the existing
rule says only an explicit reset may run again. A run SHALL NOT report itself
complete while any of the last two remain: "nothing to do right now" and "the
corpus is rebuilt" are different statements.

**A rebuild of a key SHALL NOT begin while another runner holds a live claim on
that key.** A live claim is a process writing that key at this moment, and
nothing in the store can say which checkpoint it holds. Pending work and expired
claims are **not** grounds to refuse: they are what an interrupted run leaves,
carrying them out is the point, and a runner that wakes after its lease expired
cannot land its result — a finish matches only the lease expiry its own claim
wrote.

The service SHALL also answer, for an ordered pair of keys, how many assets have
a vector under the first and none under the second. Zero means the second key
can answer for everything the first answers for. The count SHALL be taken in one
statement, so that it describes one moment rather than a walk a concurrent
upload can outrun.

Everything in this requirement SHALL be answerable without loading a model,
because the answers decide whether loading one is worth it.

**Which runner carries the work out is unchanged by any of this.** Under a
configuration where a runner of its own executes the queue, these commands
enqueue and do not execute, exactly as every other creator of work does, and
they say so.

#### Scenario: Work for a rebuild
- **WHEN** an operator asks for the work needed to rebuild a key over a corpus
- **THEN** every asset holding a vector under that key has work queued for it,
  including assets whose vector is current, because a rebuild's purpose is to
  replace vectors that already exist

#### Scenario: A rebuild asked for twice
- **WHEN** an operator asks for a rebuild's work twice, and the first request's
  work has not finished
- **THEN** the second queues nothing for the assets already covered, and carries
  out the work the first left outstanding rather than reporting that there is
  nothing to do

#### Scenario: A run interrupted before its work was done
- **WHEN** a run is killed after queueing work and before carrying it out, and
  another run of the same command follows it
- **THEN** the second run queues nothing new for those assets, carries out the
  work left waiting, and reports it as work that was already waiting rather than
  as work it queued

#### Scenario: Work another runner is holding
- **WHEN** a run's selection includes work whose claim another runner still
  holds
- **THEN** that work is not executed by this run and is reported as held, the
  run does not report itself complete, and a rebuild of that key refuses to
  begin at all

#### Scenario: Work whose retry is not yet due
- **WHEN** a run's selection includes work that failed once and is waiting out
  its backoff
- **THEN** it is neither run nor counted as done, it is reported as not yet due,
  and the run does not claim the corpus is rebuilt

#### Scenario: A runner that wakes after its lease expired
- **WHEN** work left by an interrupted run is carried out by a later run, and
  the earlier runner then tries to finish the same work
- **THEN** the late result does not land — a finish matches only the lease
  expiry its own claim wrote — so a process still holding a previous checkpoint
  cannot overwrite what the later run computed

#### Scenario: Work that has already failed
- **WHEN** a run's selection includes work that has failed terminally
- **THEN** it is neither queued again nor executed, and is reported as failed,
  because the rule that only an explicit reset runs failed work again is not
  suspended by a rebuild

#### Scenario: A deployment whose queue has its own runner
- **WHEN** either command runs where configuration says a runner of its own
  executes the queue
- **THEN** it queues the work and executes none of it, reports which
  configuration decided that, and any step that depends on the work being done
  is refused rather than assumed

#### Scenario: How far a replacement has got
- **WHEN** an operator asks how many assets have a vector under one key and none
  under another
- **THEN** the answer is a single number taken in one statement, and no model is
  loaded to produce it
