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
coordination between them: each unit of work SHALL be executed by one of them,
and a runner SHALL NOT wait for another runner's work — the rules a claim
already follows are the only mechanism, and this requirement adds none.

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
- **WHEN** two runners work one queue holding several units at the same time
- **THEN** every unit is executed exactly once, none is executed by both, and
  neither runner waits for the other

#### Scenario: A runner that stopped mid-flight
- **WHEN** a runner is stopped while it holds claimed work, and another runner
  is working the same queue
- **THEN** the work it was holding is executed by the other runner once its
  lease has expired, and it is never executed twice at the same time

### Requirement: A runner of its own stops without losing work

When a runner of its own is asked to stop, it SHALL stop taking new work, SHALL
finish the work it is holding, and SHALL then end. It SHALL NOT abandon a unit
it can still finish, and it SHALL NOT hand work back by itself: work a stopped
runner did not finish SHALL return the way any unfinished work returns, by its
lease expiring.

A second request to stop SHALL end the runner at once, without waiting for the
work in flight; what it was holding SHALL return by that same lease.

A runner that ends — either way — SHALL say so, and SHALL report what it did.

#### Scenario: Asked to stop between batches
- **WHEN** a runner waiting for work is asked to stop
- **THEN** it ends promptly, without waiting out its interval

#### Scenario: Asked to stop while working
- **WHEN** a runner holding a claimed batch is asked to stop
- **THEN** it finishes that batch — the vectors it was computing are stored —
  and then ends, taking no new work in between

#### Scenario: Asked to stop twice
- **WHEN** a runner is asked to stop a second time while finishing its batch
- **THEN** it ends at once

#### Scenario: What a stopped runner leaves behind
- **WHEN** a runner ends while holding work it did not finish
- **THEN** that work is not lost and not marked failed: it is claimable again
  once its lease expires, and the attempt it already counted stands

### Requirement: Which runner carries out the work is configured

Configuration SHALL decide which runner executes queued work: the one inside the
process that serves requests, or a runner of its own. Under the second, creating
or resetting work SHALL enqueue it and SHALL NOT execute anything inside the
serving process.

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
