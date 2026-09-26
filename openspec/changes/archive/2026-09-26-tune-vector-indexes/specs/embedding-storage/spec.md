## ADDED Requirements

### Requirement: What the vector index approximates is measured, published and bounded

The lookup is answered from an approximate index, so what it returns is not
always what an exact ranking would return. What that approximation costs SHALL
be a measured and published property of this service rather than an assumption
of whoever configured it.

For every model the store indexes, the repository SHALL carry a measurement of:
the share of the truly nearest stored vectors the index returns at the service's
default search effort, how that share and the cost of one query move as the
effort is raised across the documented range, what one query costs at the
default effort, and what the index costs to build and to hold. The comparison
SHALL cover each index family the store could be built on, not only the one it
uses, and SHALL report the same figures for each.

The ranking those shares are measured against SHALL be exact: it SHALL be read
from every stored vector of that model, never from another approximate index. A
measurement that cannot report a miss is not a measurement, so the figure SHALL
be sensitive to the index looking less far than the ranking requires.

At the service's default search effort, on a corpus of at least ten thousand
vectors per model, the share described above — the ten nearest the index
returned of the ten an exact ranking holds — SHALL be at least 0.95 **averaged
over at least fifty queries**. The measurement SHALL also report the lowest
share any single query reached; that one is published, not bounded. Over ten
neighbours a per-query bound of 0.95 would be a demand for all ten of them on
every query, which is a demand that the index stop being approximate; a mean is
what an approximate index can be held to, and the worst query is what shows
what the mean is hiding.

The measurement SHALL be reproducible by a command the repository carries, which
SHALL name the corpus it built, its size and how it was built. That command
SHALL NOT be able to alter what the service stores: it SHALL build its corpus
outside the tables the service uses, and a database holding assets, vectors and
queued work SHALL hold exactly the same ones after the command has run.

The index family the store uses and the parameters it is built with SHALL be
recorded as an architecture decision citing that measurement, together with what
the record does not decide.

#### Scenario: The ranking it is graded against is exact
- **WHEN** the measurement determines the truly nearest vectors for a query
- **THEN** the execution plan of that query shows no vector index scan, so the
  ranking is read from the store's own content rather than from the
  approximation being graded

#### Scenario: Recall at the effort the service ships with
- **WHEN** the measurement runs on a corpus of at least ten thousand vectors per
  model, at the default search effort, over at least fifty queries
- **THEN** it reports, per model and per index family, the mean share of the ten
  nearest vectors the index returned and the lowest share any single query
  reached, and for the family the store uses that mean is at least 0.95

#### Scenario: The trade-off is a curve, not a point
- **WHEN** the search effort is raised step by step across the documented range
- **THEN** the measurement reports that share and the cost of one query at every
  step, for each family, so the trade-off can be read rather than guessed

#### Scenario: A miss is reported as a miss
- **WHEN** the index is asked to look less far than the ranking requires
- **THEN** the reported share falls below 1, so a figure of 1 means the index
  found the ranking rather than that the measurement cannot tell

#### Scenario: The measurement cannot touch the store
- **WHEN** the command runs against a database holding the service's own assets,
  their vectors and queued work
- **THEN** every one of those rows is still there afterwards, unchanged, and
  nothing the command built remains

#### Scenario: The decision is recorded with its evidence
- **WHEN** the repository is read for why the store's index is what it is
- **THEN** an architecture decision names the family and its build parameters,
  cites the measured figures, and states what it does not decide
