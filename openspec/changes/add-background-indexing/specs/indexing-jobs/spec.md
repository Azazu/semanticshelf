## Purpose

The queue that turns a stored picture into vectors: what work is created and
when, how it is claimed and finished, what happens when a runner dies holding
it, and what a repeat means when delivery is at-least-once.

## ADDED Requirements

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
invisible to every other runner. Two runners claiming at the same moment SHALL
NOT take the same unit. A claim SHALL record that an attempt has begun and
SHALL set a lease that says how long the claim is good for.

#### Scenario: Two runners claim at once
- **WHEN** two runners claim from a queue holding one unit of work
- **THEN** one of them gets it and the other gets nothing, and the work is
  attempted once

#### Scenario: A claim is bounded
- **WHEN** a runner claims with a batch bound
- **THEN** it takes at most that many units, leaving the rest for others

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

### Requirement: Failure is retried a bounded number of times, then reported

Work that fails SHALL return to the queue with a delay that grows with each
attempt, until the configured number of attempts is spent; then it SHALL be
marked failed and SHALL carry a short reason. The reason SHALL name what went
wrong without a stack trace and without the contents of any file. Failed work
SHALL NOT be attempted again on its own.

#### Scenario: A transient failure
- **WHEN** work fails and attempts remain
- **THEN** it returns to the queue, becomes due later than it would have a
  moment ago, and its attempt count has grown

#### Scenario: The attempts are spent
- **WHEN** work fails on its last permitted attempt
- **THEN** it is marked failed with a reason and no further claim takes it

#### Scenario: A reason says what happened, not how
- **WHEN** work fails with an exception
- **THEN** the recorded reason is short and names the failure, and contains no
  stack trace and no file content

### Requirement: Work for an asset that is gone ends without retrying

Work whose asset no longer exists SHALL be finished as failed with a reason
naming that cause, on the first attempt, without a retry: the asset will not
come back, and repeating the work cannot succeed.

#### Scenario: The asset was deleted mid-flight
- **WHEN** an asset is deleted while work for it is being executed
- **THEN** that work ends as failed, naming the deletion as the cause, and is
  not retried

### Requirement: The state of an asset's work is visible

The service SHALL report, for each model, the state of the newest unit of work
for an asset, as part of the asset's representation and as a filter over the
listing. It SHALL also list an asset's work with its attempts, its timestamps
and its last reason. An operator SHALL be able to put chosen work back into
the queue with its attempts cleared, which is the only way failed work runs
again.

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

#### Scenario: An asset that is not stored
- **WHEN** the work of an identifier no asset carries is asked for, or a reset
  is asked for
- **THEN** the answer is 404 problem details

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
