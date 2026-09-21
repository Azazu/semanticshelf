## MODIFIED Requirements

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
