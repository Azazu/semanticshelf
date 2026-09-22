## Purpose

The operational view of the store in one request: how much is stored, how much
of it is indexed, how much work is waiting and for how long, and how many
bytes the stored originals add up to.

## ADDED Requirements

### Requirement: The service reports what it holds and what it still owes

The service SHALL answer, in one request, how many assets are stored, how much
indexing work exists per model and state, how old the oldest piece of work
still waiting is, and how many bytes the stored originals add up to — the sizes
the assets themselves record, not a measurement of the media root, so
thumbnails and any file the store does not know about are outside it. The
counts
SHALL be derived when asked rather than kept as running totals, so that they
cannot drift from the store.

An empty store SHALL be answered with zeros rather than with an error or an
absent field.

#### Scenario: A store with work in every state
- **WHEN** the statistics are requested while assets are stored, some indexed,
  some waiting and some failed
- **THEN** the answer carries the asset count, the count per model and state,
  the age of the oldest waiting work and the recorded sizes of the originals
  added up

#### Scenario: An empty store
- **WHEN** the statistics are requested and nothing is stored
- **THEN** every count is zero, no work is reported as waiting, and the answer
  is not an error

#### Scenario: Nothing is waiting
- **WHEN** the statistics are requested and no work is waiting
- **THEN** the age of the oldest waiting work is reported as absent rather than
  as zero
