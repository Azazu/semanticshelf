# indexing-jobs Specification

## Purpose
The queue that turns a stored picture into vectors: what work is created and
when, how it is claimed and finished, what happens when a runner dies holding
it, and what a repeat means when delivery is at-least-once.

## Requirements

### Requirement: Work is created with the asset, or not at all

Storing an asset SHALL create one unit of work per enabled model in the same
transaction as the asset itself. An asset SHALL NOT exist without the work its
vectors need, and work SHALL NOT exist for an asset that was never stored. The
request that created the asset SHALL NOT wait for that work.

#### Scenario: An asset is stored
- **WHEN** an asset is stored while two models are enabled
- **THEN** exactly two units of work exist for it, each naming one model, and
  each waiting to be done

#### Scenario: Storing the asset fails
- **WHEN** storing an asset fails after its work would have been created
- **THEN** neither the asset nor any work for it exists

#### Scenario: The caller does not wait
- **WHEN** an asset is uploaded
- **THEN** the answer arrives without waiting for any vector to be computed

### Requirement: Work is claimed by exactly one runner at a time

A runner SHALL take work by claiming it, and a claim SHALL make that work
invisible to every other runner — a claimer SHALL NOT wait for another
claimer's rows, it SHALL pass over them and take what is free. Two runners
claiming at the same moment SHALL NOT take the same unit. A claim SHALL record
that an attempt has begun, SHALL set a lease that says how long the claim is
good for, and SHALL give the claimer a token identifying that particular
claim.

A claimer MAY restrict a claim to the work of named assets. A restricted claim
SHALL take only work for those assets and SHALL leave every other unit exactly
as it found it, under the same rules as any claim — one runner at a time, the
same lease, the same attempt, the same order among the units it may take. A
claim that names no assets SHALL behave exactly as it did before: it takes
whatever is due.

#### Scenario: Two runners claim at once
- **WHEN** two runners claim from a queue holding one unit of work
- **THEN** one of them gets it and the other gets nothing, and the work is
  attempted once

#### Scenario: A claim is bounded
- **WHEN** a runner claims with a batch bound
- **THEN** it takes at most that many units, leaving the rest for others

#### Scenario: A claimer passes over work another claimer holds
- **WHEN** one claimer holds a due unit inside an unfinished transaction and a
  second claimer claims while it is held
- **THEN** the second claimer promptly takes a different due unit rather than
  waiting for the first to finish

#### Scenario: A claim restricted to named assets
- **WHEN** a runner claims work for named assets from a queue that also holds
  older due work for other assets
- **THEN** it takes only the named assets' work, however much older work is
  waiting, and the older work stays claimable by anyone

#### Scenario: A restricted claim finds nothing of its own
- **WHEN** a runner claims work for named assets whose work is all finished,
  while other assets' work is due
- **THEN** it takes nothing, and the other assets' work is untouched

### Requirement: A runner that dies releases its work by itself

Work claimed by a runner that never finished it SHALL become claimable again
once its lease has expired, without anything the dead runner has to do and
without an operator. Reclaiming SHALL count as a new attempt. Work whose lease
is still valid SHALL NOT be reclaimable.

#### Scenario: A lease expires
- **WHEN** work was claimed and its lease has expired without it finishing
- **THEN** the next claim takes it, exactly once, and counts another attempt

#### Scenario: A lease is still valid
- **WHEN** work was claimed a moment ago and its lease has not expired
- **THEN** no other runner can claim it

### Requirement: A vector and the finished work are one act

Writing an embedding and marking its work done SHALL happen in one
transaction, so that no state exists in which the vector is stored and the
work still looks undone, or the work looks done without its vector. Because
delivery is at-least-once, executing the same work twice SHALL leave exactly
one vector for that asset and model, with the second write replacing the
first.

A runner SHALL only be able to finish work it still owns. Finishing SHALL
carry the token from the claim, and SHALL take effect only while that token is
still the current one; if the work has since been reclaimed by another runner,
reset by an operator, or removed with its asset, the finish SHALL take effect
nowhere — neither the vector nor the state change — and the runner SHALL
discard its result rather than recreate anything.

#### Scenario: Work succeeds
- **WHEN** a unit of work is executed successfully
- **THEN** the asset has a vector for that model and the work is marked done
  with the time it finished

#### Scenario: The same work is executed twice
- **WHEN** work is executed, delivered again and executed a second time
- **THEN** the asset has exactly one vector for that model

#### Scenario: A crash between the vector and the finish
- **WHEN** a runner dies after writing a vector but before marking the work
  done
- **THEN** neither the vector nor the completion is recorded, and the work is
  attempted again after its lease expires

#### Scenario: A late finish after the work was reclaimed
- **WHEN** a runner whose lease expired finishes work that another runner has
  since claimed
- **THEN** nothing it wrote takes effect, the work stays as the second runner
  left it, and the late runner does not retry

#### Scenario: A late failure after the work was reclaimed
- **WHEN** a runner whose lease expired reports a failure for work another
  runner has since claimed
- **THEN** the work's attempts, its state and its reason are the second
  runner's, untouched by the first

#### Scenario: A late finish after the work was reset
- **WHEN** an operator resets work while a runner still holds an expired claim
  on it, and that runner then finishes
- **THEN** the reset stands: the work is still waiting, with no attempts
  against it

### Requirement: Failure is retried a bounded number of times, then reported

Work that fails SHALL return to the queue with a delay that grows with each
attempt, until the configured number of attempts is spent; then it SHALL be
marked failed and SHALL carry a reason.

The reason SHALL name the failure's class. It SHALL include the failure's
message only when the service itself raised that failure, and therefore wrote
that message; for any other failure the class alone SHALL be recorded, because
no rule can tell which parts of a message a library built out of the bytes it
was reading. The reason SHALL be bounded to at most two kilobytes, with any
truncation visible, and SHALL never contain a stack trace. Failed work SHALL
NOT be attempted again on its own.

#### Scenario: A transient failure
- **WHEN** work fails and attempts remain
- **THEN** it returns to the queue, becomes due later than it would have a
  moment ago, and its attempt count has grown

#### Scenario: The attempts are spent
- **WHEN** work fails on its last permitted attempt
- **THEN** it is marked failed with a reason and no further claim takes it

#### Scenario: A reason says what happened, not how
- **WHEN** work fails with an exception
- **THEN** the recorded reason names the failure's class, carries a message
  only under the rule above, and contains no stack trace

#### Scenario: A failure the service did not raise
- **WHEN** work fails with an exception from a library whose message holds
  bytes read from the stored file
- **THEN** the recorded reason is that exception's class name alone, and none
  of those bytes appear in it

#### Scenario: A failure the service raised itself
- **WHEN** work fails because the model it names is not enabled
- **THEN** the recorded reason carries both the class and the message the
  service wrote, because that message is one it controls

#### Scenario: A failure with an enormous message
- **WHEN** work fails with a message longer than the recorded reason may be
- **THEN** the reason is stored at the bound and remains readable

### Requirement: Work for an asset that is gone disappears with it

Deleting an asset removes everything derived from it, including its work, so
there is no record left to carry a failure. A runner executing such work SHALL
discover it when its finish takes effect nowhere; it SHALL discard its result,
SHALL NOT recreate the work, SHALL NOT retry, and SHALL NOT answer with a
server error. Nothing SHALL remain afterwards: no vector, no work, no file.

#### Scenario: The asset was deleted mid-flight
- **WHEN** an asset is deleted while work for it is being executed
- **THEN** the work is gone with the asset, the runner's result is discarded,
  and no vector exists for that asset

#### Scenario: The runner survives it
- **WHEN** a runner's work vanishes under it in that way
- **THEN** the runner records the fact and continues with the rest of its
  batch

### Requirement: The state of an asset's work is visible

The service SHALL report, for each model, the state of the newest unit of work
for an asset, as part of the asset's representation and as a filter over the
listing. It SHALL also list an asset's work with its attempts, its timestamps —
including, while a runner holds it, when that claim stops being the owner — and
its last reason. An operator SHALL be able to put chosen work back into the
queue with its attempts cleared, which is the only way failed work runs again.
Naming no models SHALL reset all of an asset's work and naming an empty set of
them SHALL reset none: a selection of nothing is a selection, not the absence
of one.

#### Scenario: An asset that has been indexed
- **WHEN** an asset whose work has all succeeded is read
- **THEN** its representation reports every enabled model as done

#### Scenario: Listing by the state of the work
- **WHEN** assets are listed with a filter naming a model and a state
- **THEN** exactly the assets whose newest work for that model is in that
  state come back

#### Scenario: Failed work is reset
- **WHEN** an operator asks for an asset's failed work to run again
- **THEN** that work returns to the queue with no attempts against it, and the
  request says so

#### Scenario: A reset that selects nothing
- **WHEN** an operator asks for an asset's work to run again and names an empty
  set of models
- **THEN** no work is reset, and the answer says that none was

#### Scenario: Work a runner is holding
- **WHEN** the work of an asset is listed while a runner holds a claim on it
- **THEN** the answer says when that claim stops being the owner, and says
  nothing of the kind for work at rest

#### Scenario: An asset that is not stored
- **WHEN** the work of an identifier no asset carries is asked for, or a reset
  is asked for
- **THEN** the answer is 404 problem details

### Requirement: A stored file is inspected again before it is decoded

Executing work SHALL read the stored original through the same inspection an
upload goes through: the format detected from the bytes, the pixel cap and the
minimum side applied again, and the pixels converted to three channels before
the model sees them. A file that no longer satisfies those rules SHALL fail
its work rather than be decoded, because the checks made at upload say nothing
about a file that has changed on disk since.

#### Scenario: A file replaced on disk with something unacceptable
- **WHEN** the stored original of an asset is replaced with a file that would
  not be accepted at upload
- **THEN** the work fails with a reason, and no vector is written

#### Scenario: A file replaced with a picture beyond the caps
- **WHEN** the stored original is replaced with a picture larger than the
  configured pixel cap
- **THEN** the work fails before those pixels are decoded

#### Scenario: A picture that is not three-channel
- **WHEN** the stored original is greyscale or has an alpha channel
- **THEN** it is converted before the model sees it, and the work succeeds

### Requirement: Indexing does not block the service

Executing work SHALL NOT block the thread that serves requests: the model runs
where model work belongs, and a runner inside the API process SHALL drain at
most a bounded batch per run rather than looping while work remains.

#### Scenario: A burst of uploads
- **WHEN** several assets are uploaded in quick succession
- **THEN** every response is answered without waiting for the vectors, and the
  service keeps answering other requests while work is executed

#### Scenario: More work than one batch
- **WHEN** more work is waiting than the batch bound allows
- **THEN** a single run takes at most that many units and the rest stays
  queued for the next one
