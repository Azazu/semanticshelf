## ADDED Requirements

### Requirement: A key's vectors are retired only when another key can answer for them

Deleting a key's vectors is irreversible: the pictures remain, the work to
rebuild them is hours of a machine's time, and nothing in the store remembers
what they were. So the service SHALL delete the vectors of a key only when both
hold:

- **the replacement is complete** — no asset has a vector under the key being
  retired and none under the key replacing it, counted at the moment of the
  deletion rather than earlier in the run;
- **an operator asked for it in as many words** — a deletion SHALL NOT be the
  default behaviour of a command whose other half is additive.

A request to retire a key whose replacement is incomplete SHALL be refused, and
SHALL say how many assets are not yet covered. Refusing is the whole point: the
corpus a search answers from is the thing at risk, and an operator who ran the
fill and did not notice it stopped is exactly the case this exists for.

Retiring a key removes its vectors. It does not remove the key from the schema's
allowlist, which is a migration, nor from the models a build runs, which is
configuration — a deployment that retires a key and leaves it enabled will queue
work for it on the next upload, and that is the operator's decision to make
deliberately rather than a consequence this command imposes.

#### Scenario: Retiring a key whose replacement is complete
- **WHEN** an operator asks to retire a key, every asset that has a vector under
  it also has one under the replacing key, and the request says so explicitly
- **THEN** the key's vectors are deleted and the assets, their files and every
  other key's vectors are untouched

#### Scenario: Retiring a key whose replacement is not complete
- **WHEN** an operator asks to retire a key and some assets have no vector under
  the replacing key
- **THEN** nothing is deleted, and the refusal names how many assets are not yet
  covered

#### Scenario: A retirement nobody asked for
- **WHEN** a fill is run without an explicit instruction to retire
- **THEN** no vector is deleted, whatever the state of the replacement, and the
  run reports what a retirement would do

#### Scenario: The corpus grew during the run
- **WHEN** assets were uploaded while the fill was running, so that the
  replacement was complete when the fill ended and is not at the moment of the
  deletion
- **THEN** the deletion is refused on the count taken at that moment, not on the
  earlier one
