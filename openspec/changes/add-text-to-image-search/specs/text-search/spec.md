## Purpose

Finding pictures by describing them: what a query may be, how the service turns
it into a ranking, what a result says about itself, and where a page of results
begins and ends.

## ADDED Requirements

### Requirement: A text query is answered by ranking the stored vectors of one model

The service SHALL accept a text query and answer it with the stored assets
whose vectors of the search model are nearest to the query's vector, closest
first. The query SHALL be embedded with that model's text side, and compared
only with vectors of that same model: a score SHALL never be computed between
vectors of different models.

The answer SHALL name the model it used, because a score has no meaning without
it.

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

### Requirement: A query is bounded, and a shortened query says so

A query SHALL be required and non-empty once trimmed, and SHALL be refused with
422 problem details when it is missing, empty, or longer than the configured
maximum. A model that cannot represent the whole query SHALL NOT silently
answer a shorter one: when the query was cut to fit the model, the answer SHALL
say so.

#### Scenario: No query at all
- **WHEN** a search is requested without a query, or with one that is empty
  after trimming
- **THEN** the answer is 422 problem details naming the parameter

#### Scenario: A query beyond the maximum length
- **WHEN** a query longer than the configured maximum is searched for
- **THEN** the answer is 422 problem details naming the bound

#### Scenario: A query the model had to cut
- **WHEN** a query longer than the model's context is searched for
- **THEN** the answer is a normal page of results and states that the query was
  truncated

### Requirement: A result carries the asset and its score

Each result SHALL carry the asset's representation, exactly as every other
endpoint returns it, and a score derived from the cosine distance between the
query and that asset's vector, where a larger score means a closer match. The
score SHALL be in the range that cosine similarity allows.

Results SHALL be ordered by score, highest first, and results of equal score
SHALL be ordered by the asset's identifier, so that a page is fully determined
and two requests for the same page of an unchanged store return the same items
in the same order.

A group of results with **identical** scores that does not fit on one page MAY
be divided between pages arbitrarily: which of them each page holds is the
index's choice, so paging through such a group MAY show one of its members
twice or not at all. Each page SHALL still be repeatable — the same page of the
same query over an unchanged store answers the same way — and a caller who
needs such a group whole asks for a page large enough to hold it. Identical
scores mean two different pictures whose vectors match to the last bit, which
the content hash makes impossible for identical bytes and a real model does not
otherwise produce.

#### Scenario: What an item says
- **WHEN** a search returns an asset
- **THEN** the item carries that asset's representation and its score

#### Scenario: Two assets with the same score
- **WHEN** two assets are equally near the query and both fall on one page
- **THEN** their order is decided by their identifiers, and is the same in
  every request for that page

#### Scenario: The same page asked for twice
- **WHEN** the same page of the same query is requested twice over an unchanged
  store
- **THEN** it holds the same items in the same order

### Requirement: A threshold filters the page it is applied to

A minimum score MAY be given, and SHALL drop from the answer every result whose
score is below it. The threshold SHALL be applied to the results the page would
otherwise contain: a page may come back shorter than the requested size, and
the service SHALL NOT read further into the ranking to fill it.

#### Scenario: A threshold that excludes some results
- **WHEN** a search with a minimum score is requested and some of the page's
  results are below it
- **THEN** those results are absent, the rest are unchanged and in the same
  order, and the page is shorter

#### Scenario: A threshold nothing reaches
- **WHEN** a search with a minimum score higher than every result's score is
  requested
- **THEN** the answer is an empty page rather than an error

### Requirement: A page is bounded, and says whether more exist

The answer SHALL carry the items, the page size, the offset and whether more
items exist beyond the page, and SHALL NOT carry a total count. Whether more
exist SHALL be determined by looking one item beyond the page rather than by
counting.

The page size SHALL have a default and a maximum. A page whose size and offset
together reach beyond the depth the index can answer accurately SHALL be
refused with 422 problem details naming that bound, rather than answered with a
silently worse ranking.

#### Scenario: More results exist
- **WHEN** a page is requested and the ranking holds more results beyond it
- **THEN** the answer says so, and carries no total count

#### Scenario: The last page
- **WHEN** the last page of a ranking is requested
- **THEN** the answer says that no more exist

#### Scenario: A page beyond the maximum size
- **WHEN** a page larger than the maximum is requested
- **THEN** the answer is 422 problem details naming the parameter

#### Scenario: A page too deep to answer
- **WHEN** a page whose size and offset together exceed the searchable depth is
  requested
- **THEN** the answer is 422 problem details naming that bound, and no search
  is run

### Requirement: Search is answered from the index, at the depth it is asked for

Every search SHALL be answered from the vector index of the search model rather
than by reading every stored vector. The index's search effort SHALL be set for
each query to at least the depth that query needs — the page's size plus its
offset — so that a deeper page does not quietly return a worse ranking than a
shallow one.

#### Scenario: The index answers the query
- **WHEN** the execution plan of a search is inspected
- **THEN** it shows a scan of the search model's vector index and no sequential
  scan of the stored vectors

#### Scenario: A deep page is searched as deeply as it is asked
- **WHEN** a page deep in the ranking is requested
- **THEN** the search effort for that query is at least the size and offset it
  asks for

### Requirement: An asset is searchable while it has a vector

An asset SHALL be findable by search exactly while it has a vector for the
search model. Work queued again for an asset that already has one SHALL NOT
remove it from search while that work waits: the vector it has is the answer
until a new one replaces it.

#### Scenario: An asset whose work was queued again
- **WHEN** an asset that has a vector has its indexing work reset and searched
  for before that work runs
- **THEN** it is still found, with the score its existing vector gives

#### Scenario: An asset that has never been indexed
- **WHEN** an asset whose work has not yet produced a vector is searched for
- **THEN** it does not appear in any result
