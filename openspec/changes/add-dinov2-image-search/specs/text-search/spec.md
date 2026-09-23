## MODIFIED Requirements

### Requirement: A text query is answered by ranking the stored vectors of one model

The service SHALL accept a text query and answer it with the stored assets
whose vectors of the search model are nearest to the query's vector, closest
first. The query SHALL be embedded with that model's text side, and compared
only with vectors of that same model: a score SHALL never be computed between
vectors of different models.

The answer SHALL name the model it used, because a score has no meaning without
it. A search MAY be asked for a particular model, and SHALL then use that one:
the choice SHALL NOT fall back to another model, quietly or otherwise.

A model SHALL be usable for a query only if it can take that kind of query — a
query in words needs a model with a text side, a query that is a picture needs a
model with an image side. A named model that this build does not run SHALL be
refused as unavailable, and a named model that cannot take the kind of query it
was given SHALL be refused as a bad request naming what it can take. This rule
holds for every search the service offers, whatever the query is made of.

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

#### Scenario: A model that cannot take that kind of query
- **WHEN** a text query names a model with no text side
- **THEN** the answer is 422 problem details naming what that model can be
  asked, and no search is run

#### Scenario: A model this build does not run
- **WHEN** a search names a model this build does not run
- **THEN** the answer is 503 problem details naming it, and no search is run
