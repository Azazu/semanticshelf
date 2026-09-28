## MODIFIED Requirements

### Requirement: A text query is answered by ranking the stored vectors of one model

The service SHALL accept a text query and answer it with the stored assets
whose vectors of the search model are nearest to the query's vector, closest
first. The query SHALL be embedded into the search model's space, and compared
only with vectors of that same space: a score SHALL never be computed between
vectors that do not share one.

What embeds the query is either the search model's own text side or a **query
encoder** that declares that model's space as the one it answers in. A query
encoder owns no stored vector: it exists to put words into a space whose
pictures are already there. Its claim to that space is a claim about what it
was trained to do, and this repository SHALL hold it to published measurements
rather than to the assertion — the languages a build names as supported SHALL
be the ones whose numbers are published, and the rest SHALL be named as
unmeasured rather than implied.

The answer SHALL name the model whose vectors were ranked, because a score has
no meaning without it, and SHALL also name the encoder that embedded the query
whenever that is not the model's own text side — two scores are comparable only
when both were produced by the same pair.

A search MAY be asked for a particular model or query encoder, and SHALL then
use that one: the choice SHALL NOT fall back to another, quietly or otherwise.

A model SHALL be usable for a query only if it can take that kind of query — a
query in words needs a text side, a query that is a picture needs an image
side. A named model or encoder that this build does not run SHALL be refused as
unavailable, and a named one that cannot take the kind of query it was given
SHALL be refused as a bad request naming what it can take. This rule holds for
every search the service offers, whatever the query is made of.

#### Scenario: A query finds what it describes
- **WHEN** a query is searched for and the store holds assets whose vectors are
  near it
- **THEN** those assets come back ordered from nearest to furthest, and the
  answer names the model that ranked them

#### Scenario: A store with nothing indexed
- **WHEN** a query is searched for and no asset has a vector for the search
  model
- **THEN** the answer is an empty page rather than an error

#### Scenario: Vectors of another model are not searched
- **WHEN** assets carry vectors under more than one model and a query is
  searched for
- **THEN** only the search model's vectors are ranked, and no asset appears by
  virtue of another model's vector

#### Scenario: A search that names its model
- **WHEN** a search names a model this build runs and that can take that kind of
  query
- **THEN** it is answered by that model's vectors, and the answer names it

#### Scenario: A search that names a query encoder
- **WHEN** a text search names a query encoder this build runs
- **THEN** the query is embedded by that encoder, ranked against the vectors of
  the storage model whose space the encoder declares, and the answer names both

#### Scenario: A query encoder this build does not run
- **WHEN** a search names a query encoder this build does not run
- **THEN** the answer is 503 problem details naming it, and no search is run

#### Scenario: A query encoder is not a place to store vectors
- **WHEN** work, a vector or an index is looked for under a query encoder's name
- **THEN** there is none: nothing is ever written to the store under it, and it
  appears in no count of what the service holds

#### Scenario: A model that cannot take that kind of query
- **WHEN** a text query names a model with no text side
- **THEN** the answer is 422 problem details naming what that model can be
  asked, and no search is run

#### Scenario: A model this build does not run
- **WHEN** a search names a model this build does not run
- **THEN** the answer is 503 problem details naming it, and no search is run

#### Scenario: The languages a build claims are the ones it measured
- **WHEN** the documentation states which languages a query may be written in
- **THEN** each named language has a published measurement behind it, taken by
  a command in this repository, and every other language the encoder accepts is
  described as untested
