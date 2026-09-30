## ADDED Requirements

### Requirement: A key's vectors are retired only when another key can answer for them

Deleting a key's vectors is irreversible: the pictures remain, the work to
rebuild them is hours of a machine's time, and nothing in the store remembers
what they were. So the service SHALL delete the vectors of a key only when all
of these hold:

- **the replacement is complete** — no asset has a vector under the key being
  retired and none under the key replacing it, established **in the statement
  that deletes**, not by an earlier reading of the same fact;
- **nothing is still owed** — no work for the replacing key is waiting, running
  or failed, because coverage that a queue is about to change is not coverage;
- **an operator asked for it in as many words** — a deletion SHALL NOT be the
  default behaviour of a command whose other half is additive.

**Two retirements SHALL NOT be able to undo each other.** Coverage inside a
statement is a snapshot, not an agreement: two retirements in opposite
directions can each see themselves covered and delete disjoint rows, leaving an
asset with neither vector. A retirement SHALL therefore hold the queue's
per-model advisory lock for **both** keys, taken in a fixed order that does not
depend on which is being retired, for the whole of the coverage test and the
delete. The same lock is what the queue takes before it selects work, so a
retirement and a fill of either key cannot overlap either.

A request to retire a key whose replacement is incomplete SHALL be refused, and
SHALL say how many assets are not yet covered and whether work for them is
outstanding — an operator who ran the fill under a configuration that only
enqueues needs to be told that, not left to read a number.

Retiring a key removes its vectors. It does not remove the key from the schema's
allowlist, which is a migration, nor from the models a build runs, which is
configuration — a deployment that retires a key and leaves it enabled will queue
work for it on the next upload, and that is the operator's decision to make
deliberately rather than a consequence this command imposes.

#### Scenario: Retiring a key whose replacement is complete
- **WHEN** an operator asks to retire a key, every asset that has a vector under
  it also has one under the replacing key, no work for the replacing key is
  outstanding, and the request says so explicitly
- **THEN** the key's vectors are deleted and the assets, their files and every
  other key's vectors are untouched

#### Scenario: Retiring a key whose replacement is not complete
- **WHEN** an operator asks to retire a key and some assets have no vector under
  the replacing key
- **THEN** nothing is deleted, and the refusal names how many assets are not yet
  covered

#### Scenario: A replacement the queue has not finished
- **WHEN** every asset is covered but work for the replacing key is still
  waiting or running
- **THEN** nothing is deleted, and the refusal says the queue has not finished,
  because a count taken while work is outstanding describes a corpus that is
  still changing

#### Scenario: A retirement nobody asked for
- **WHEN** a fill is run without an explicit instruction to retire
- **THEN** no vector is deleted, whatever the state of the replacement, and the
  run reports what a retirement would do

#### Scenario: An asset that gained the old key's vector during the run
- **WHEN** an asset is given a vector under the key being retired while the fill
  is running, so that it is covered at the fill's end and not at the moment of
  the delete
- **THEN** the deletion is refused on the count taken inside the deleting
  statement, not on the earlier one

#### Scenario: Two retirements in opposite directions
- **WHEN** one retirement of key A in favour of B and one of B in favour of A
  are attempted at the same time
- **THEN** they do not overlap: each holds both keys' locks in the same order,
  so the second sees what the first did and refuses, and no asset is left
  without a vector under either key
