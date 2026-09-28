## ADDED Requirements

### Requirement: A model key earns its place by measurement

A model key is permanent: it is part of an embedding's identity, it takes a
value in the schema's allowlist, it costs an index and a vector for every asset
the service holds, and it queues work for every upload. So before a key is
added, this repository SHALL publish what that model answers **that the keys
already present do not**, and SHALL do it as a measurement rather than as a
description.

The measurement SHALL be produced by a command in the repository, over a corpus
the command builds or names, so that anyone can re-run it and get the same
answer. Its bound SHALL be fixed before the numbers are seen, and SHALL be
about the margin over what the service already runs — a key that is only
marginally better than an existing one at the same question has not earned a
migration.

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

#### Scenario: A candidate that duplicates a key already present
- **WHEN** the measurement shows the candidate does not clear the margin
- **THEN** the key is not added, and the numbers are published in the record
  that refused it, so the question does not have to be asked again from nothing

#### Scenario: The measurement can be re-run
- **WHEN** somebody re-runs the published command against the corpus it names
- **THEN** they get the same numbers, because the corpus is built by that
  command or named exactly, and the checkpoint it loads is pinned
