## ADDED Requirements

### Requirement: The store records which revision each key's vectors were built with

Vectors of one model key are compared with each other, and that is meaningful
only while they come from one checkpoint. The key alone cannot say which, so the
store SHALL record, **per model key**, the revision the vectors under that key
were built with.

The record SHALL be written in the same transaction as the first vector stored
under that key, so it describes what was actually stored rather than what was
configured at some later moment. It SHALL NOT be rewritten by a later insert: a
record that followed the configuration would agree with it always and detect
nothing.

The record is per key, not per vector. The revision is the same for every row a
key holds while the record stands, and putting it on each row would make it part
of an embedding's identity, which ADR-001 gives to the asset and the key.

A corpus stored before this rule existed has no such record and none can be
reconstructed. Its record SHALL read `unknown` — a stated absence rather than a
guess, and one that never equals any configured revision.

#### Scenario: The first vector under a key records its revision
- **WHEN** the first embedding for a model key is stored
- **THEN** the store holds one record for that key naming the revision the
  embedder was loaded at, written in the transaction that stored the vector

#### Scenario: Later vectors do not rewrite the record
- **WHEN** a further embedding is stored under a key that already has a record
- **THEN** the record is unchanged, whatever the configuration now says

#### Scenario: A corpus older than the rule
- **WHEN** the rule is introduced to a store that already holds vectors under a
  key
- **THEN** that key's record reads `unknown`, which no configured revision
  equals
