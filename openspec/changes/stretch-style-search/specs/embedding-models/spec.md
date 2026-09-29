## ADDED Requirements

### Requirement: A model key earns its place by measurement

A model key is permanent: it is part of an embedding's identity, it takes a
value in the schema's allowlist, it costs an index and a vector for every asset
the service holds, and it queues work for every upload. So before a key is
added, this repository SHALL publish what that model answers **that the keys
already present do not**, and SHALL do it as a measurement rather than as a
description.

The comparison SHALL cover **every key the service already stores vectors of
that kind under**, not a key chosen for the comparison: a candidate that beats
one incumbent and duplicates another has not answered the question.

The measurement SHALL be produced by a command in the repository, over a corpus
the command builds or names, so that anyone can re-run it and get the same
answer. Its bound SHALL be fixed before the numbers are seen, and SHALL be
about the margin over the best of those keys — a key that is only marginally
better than an existing one at the same question has not earned a migration.

The number the bound is read on SHALL be one that a model's own similarity scale
cannot move. Models differ in how widely they spread cosine similarity, so a
statistic built from the size of the scores can rank a candidate above an
incumbent that in fact orders results the other way round. A statistic about the
**order** a model puts candidates in survives that; any other number may be
published beside it, as a diagnostic that decides nothing.

A candidate that does not clear the bound SHALL NOT be added, and the
measurement SHALL be published anyway, in the record that decided it. "Not
added" is an outcome of the same standing as "added": what this requirement
forbids is a key whose value nobody measured.

This requirement is about keys the service **stores** vectors under. It does
not govern a query encoder, which stores nothing and whose own claim —
answering in another key's space — is measured under the rule it already has.

#### Scenario: A candidate that answers something new
- **WHEN** a model is proposed as a new key and a published measurement shows
  it clears the stated margin over every key the service already runs
- **THEN** the key may be added, and the record that admits it cites the
  measurement and the command that produced it

#### Scenario: A statistic a model's own scale can move
- **WHEN** the candidate is ranked above an incumbent by a statistic computed
  from how large the similarity scores are, rather than from the order they put
  results in
- **THEN** that statistic does not decide: the bound is read on a number that
  survives rescaling, and the record publishes both and says which one decided

#### Scenario: A candidate that duplicates a key already present
- **WHEN** the measurement shows the candidate does not clear the margin
- **THEN** the key is not added, and the numbers are published in the record
  that refused it, so the question does not have to be asked again from nothing

#### Scenario: The measurement can be re-run
- **WHEN** somebody re-runs the published command against the corpus it names
- **THEN** they get the same numbers whenever they have the same corpus and the
  same checkpoints, and the record tells them whether they do: it publishes a
  digest of the corpus's bytes and the identity of every checkpoint the run
  loaded

#### Scenario: An input the repository does not pin
- **WHEN** the measurement loads a checkpoint whose revision this repository
  does not fix — a name a deployment configures rather than a pinned commit
- **THEN** the record SHALL print what that name resolved to on the machine
  that produced the numbers, and SHALL NOT present it as fixed; a reader
  comparing two runs can then see which input differed instead of trusting that
  none did
