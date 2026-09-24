## ADDED Requirements

### Requirement: The queue has a runner that is a process of its own

The service SHALL provide a runner that is not part of the process serving
requests. It SHALL take due work in bounded batches, by the same claiming,
executing and finishing every runner uses, and it SHALL keep going: when a batch
is worked through it SHALL look for more, and when nothing is due it SHALL wait
a bounded interval and look again rather than exiting or asking the database
continuously. How long that wait is SHALL be configurable.

It SHALL also be able to take a single batch and stop, so that a run can be
scripted or tested without a signal.

Several such runners SHALL be able to work one queue at the same time with no
coordination between them. The guarantee this gives is the one the queue has
always given, and it is not exactly-once: while a unit's lease is valid it is
held by one runner and no other may take it, delivery is **at-least-once**, a
completion SHALL take effect only while the claim it came from still owns the
unit, and the stored effect SHALL be idempotent so that a unit executed more
than once leaves one result. A runner SHALL NOT wait for work another runner
holds. The rules a claim already follows are the only mechanism, and this
requirement adds none.

#### Scenario: Work waiting is worked through
- **WHEN** a runner of its own is started against a queue holding more work than
  one batch
- **THEN** it works through all of it, batch after batch, without being asked
  again

#### Scenario: Nothing is due
- **WHEN** the queue holds nothing a runner may take
- **THEN** the runner waits its configured interval and looks again, and it
  neither exits nor queries continuously

#### Scenario: A single batch on request
- **WHEN** a runner is asked for one batch
- **THEN** it takes at most one batch, finishes what it took, and exits —
  reporting how much it did

#### Scenario: Two runners on one queue
- **WHEN** two runners work one queue holding several units at the same time,
  every lease outlives the work it covers and nothing fails
- **THEN** each unit is executed by one of them and ends finished, the store
  holds one result per unit, and both runners make progress rather than one
  waiting for the other

#### Scenario: A lease expires under a runner that is still working
- **WHEN** a unit's lease expires while the runner that claimed it is still
  computing, and another runner claims in the meantime
- **THEN** the second runner may execute the same unit — that is the
  at-least-once delivery the queue promises — the store still ends with one
  result, and the first runner's completion, arriving after it lost the claim,
  changes nothing and is reported as discarded rather than retried

#### Scenario: A runner that was terminated mid-flight
- **WHEN** a runner **ends** while holding claimed work — it is gone, not
  paused — and another runner is working the same queue
- **THEN** the work it was holding becomes claimable once its lease expires, is
  executed by the other runner, counts the second attempt, and leaves one
  result in the store. No claim is made here about a runner that was merely
  slow or paused: such a runner may still be computing, and what protects the
  store from it is the rule above — its completion lands nowhere once it has
  lost the claim, and the write is idempotent

### Requirement: A runner of its own stops without losing work

When a runner of its own is asked to stop, it SHALL stop taking new work, SHALL
finish the work it is holding, and SHALL then end. It SHALL NOT abandon a unit
it can still finish, and it SHALL NOT hand work back by itself: work a stopped
runner did not finish SHALL return the way any unfinished work returns, by its
lease expiring.

A second request to stop SHALL end the runner at once, without waiting for the
work in flight; what it was holding SHALL return by that same lease.

A runner that ends **gracefully** SHALL report what it did. A runner ended by
the second request SHALL say that it was forced, and SHALL NOT be required to
report more: it is ending at once, and a summary it had to collect first would
be a delay the second request exists to remove.

#### Scenario: Asked to stop between batches
- **WHEN** a runner waiting for work is asked to stop
- **THEN** it ends promptly, without waiting out its interval

#### Scenario: Asked to stop while working
- **WHEN** a runner holding a claimed batch is asked to stop
- **THEN** it finishes that batch — the vectors it was computing are stored —
  and then ends, taking no new work in between

#### Scenario: Asked to stop twice
- **WHEN** a runner is asked to stop a second time while finishing its batch
- **THEN** it ends at once, saying only that it was forced

#### Scenario: What a stopped runner leaves behind
- **WHEN** a runner ends while holding work it did not finish
- **THEN** that work is not lost and not marked failed: it is claimable again
  once its lease expires, and the attempt it already counted stands

### Requirement: Which runner carries out the work is configured

Configuration SHALL decide which runner executes queued work: the one that lives
in the process which created the work, or a runner of its own. Under the second,
anything that creates or resets work SHALL enqueue it and SHALL NOT execute it
itself — neither the process serving requests nor an operator's command that
would otherwise finish the work it just created.

The contract of the interface SHALL be identical under both: the same responses,
the same states, the same guarantee that work exists as soon as the thing it
belongs to does. What differs is only which process does the work and when.

The default SHALL be the runner that needs nothing else to be started, so that a
deployment that was never told about runners still indexes what it accepts.

#### Scenario: The default deployment indexes by itself
- **WHEN** the service is run without being told which runner to use, and an
  asset is created
- **THEN** its work is carried out without any other process being started

#### Scenario: Configured for a runner of its own
- **WHEN** the service is configured to use a runner of its own, and an asset is
  created
- **THEN** the work is queued and nothing is executed inside the serving
  process; the work waits for that runner

#### Scenario: A command that would carry out its own work
- **WHEN** an operator's command that normally finishes the work it created is
  run while a runner of its own is configured
- **THEN** it creates the work, reports it as queued, and executes none of it —
  and a command already told to leave the work queued behaves the same way, so
  the two instructions cannot contradict each other

#### Scenario: The same answers either way
- **WHEN** the same request is made under each configuration
- **THEN** the responses are the same, including what they say about the state
  of the work at the moment they are answered

## MODIFIED Requirements

### Requirement: Indexing does not block the service

Executing work SHALL NOT block the thread that serves requests: the model runs
where model work belongs, and a runner **inside the serving process** SHALL take
at most a bounded batch per run rather than looping while work remains — it
shares its process with the requests, and a run that drained the queue would
never end.

A runner that is a process of its own SHALL NOT be bound that way: it exists to
keep going, and it takes batch after batch for as long as it runs. The bound on
one batch stays, because it is what lets several runners share a queue and what
keeps a stop from having to wait for an unbounded amount of work.

#### Scenario: A burst of uploads
- **WHEN** several assets are uploaded in quick succession
- **THEN** every response is answered without waiting for the vectors, and the
  service keeps answering other requests while work is executed

#### Scenario: More work than one batch
- **WHEN** more work is waiting than the batch bound allows, and the runner is
  the one inside the serving process
- **THEN** a single run takes at most that many units and the rest stays
  queued for the next one
