# text-search Specification

## Purpose
Finding pictures by describing them: what a query may be, how the service turns
it into a ranking, what a result says about itself, and where a page of results
begins and ends.

## Requirements

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

### Requirement: A query is bounded, and a shortened query says so

A query SHALL be required and non-empty once trimmed, and SHALL be refused with
422 problem details when it is missing, empty, or longer than the configured
maximum. The maximum SHALL be measured on the trimmed query, so that padding is
never counted against a caller; a separate, far larger bound on the raw
parameter SHALL keep padding from making the request unbounded. A model that
cannot represent the whole query SHALL NOT silently answer a shorter one: when
the query was cut to fit the model, the answer SHALL say so.

#### Scenario: No query at all
- **WHEN** a search is requested without a query, or with one that is empty
  after trimming
- **THEN** the answer is 422 problem details naming the parameter

#### Scenario: A query beyond the maximum length
- **WHEN** a query longer than the configured maximum is searched for
- **THEN** the answer is 422 problem details naming the bound

#### Scenario: A query whose padding carries it past the maximum
- **WHEN** a query is searched for whose trimmed length is exactly the maximum
  but whose raw parameter is longer because of surrounding whitespace
- **THEN** it is answered normally rather than refused for its length

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
SHALL be ordered by the asset's identifier. Every page the service returns SHALL
carry that order, so what a page contains is never ambiguous about how it is
arranged.

Which results a page contains is a different question, and the answer is bounded
by what an approximate index can promise. For a store that has not changed and
a page across which no group of identical scores falls, two requests for that
page SHALL return the same items. Where a group of identical scores does fall
across a page's boundary, the service SHALL NOT promise which of that group's
members the page holds: they MAY differ between requests, and paging through
such a group MAY show one of its members twice or not at all. A caller who needs
such a group whole asks for a page large enough to hold it, which also raises
the search effort that decides how much of the group the index returns.

Identical scores do not require identical vectors: any two vectors at the same
angle to the query score the same. The service therefore does not treat a tie
as impossible — it states what it can and cannot promise about one, because an
approximate index may return some members of a tied group and not others
however deep the page asks.

#### Scenario: What an item says
- **WHEN** a search returns an asset
- **THEN** the item carries that asset's representation and its score

#### Scenario: Two assets with the same score
- **WHEN** two assets are equally near the query and both fall on one page
- **THEN** their order is decided by their identifiers, and is the same in
  every request for that page

#### Scenario: The same page asked for twice
- **WHEN** a page across which no group of identical scores falls is requested
  twice over an unchanged store
- **THEN** it holds the same items in the same order

#### Scenario: A page whose edge cuts a group of identical scores
- **WHEN** a page's boundary falls inside a group of results with identical
  scores
- **THEN** whichever of that group the page holds are in identifier order, and
  the service promises nothing about which of them those are

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

That depth SHALL leave room for the item beyond the page: the index produces a
bounded number of candidates for one query, the item that decides whether more
exist is one of them, and so the deepest page the service accepts SHALL end one
item short of that ceiling. The service SHALL NOT accept a page whose answer it
could only complete by guessing whether more exist.

When a search is narrowed, how far the index must look to fill a page is no
longer decided by the page's depth alone: the assets that satisfy the narrowing
may lie arbitrarily deep in the ranking. The service SHALL bound that work, and
SHALL say in the answer when it stopped at that bound rather than at the end of
the ranking. It SHALL NOT present such an answer as though the ranking held
nothing more.

That report SHALL be decided by what the search itself found — whether it
produced the results the answer needed, including the one beyond the page that
says whether more exist — and NOT by how the answer looks afterwards. A full
page SHALL NOT be taken as proof that the search was not cut short, and a page
shortened by the threshold SHALL NOT be reported as a search that was.

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

#### Scenario: The deepest page the service accepts
- **WHEN** the deepest page within the bound is requested
- **THEN** it is answered, and the search effort for it covers the page and the
  item beyond it that says whether more exist

#### Scenario: A narrowed search that reaches its bound
- **WHEN** a search narrowed to something rare stops at the bound on how far it
  may look, before it has filled the page
- **THEN** the answer says that it stopped there, so that a short page is not
  read as the end of the ranking

#### Scenario: A full page that the search was cut short of completing
- **WHEN** a narrowed search stops at its bound having found exactly as many
  results as the page holds, while more satisfying the narrowing exist beyond
  what it reached
- **THEN** the answer still says that it stopped at its bound, rather than
  saying that nothing follows the page

#### Scenario: An empty page deep in a narrowed ranking
- **WHEN** a narrowed search at a large offset comes back empty, once because
  the scan stopped at its bound before reaching that offset and once because the
  ranking holds fewer results than the offset skips
- **THEN** the first says that the search stopped at its bound and the second
  does not: an empty page is not evidence either way, and what the search
  reached decides it

#### Scenario: A page the threshold shortened
- **WHEN** a narrowed search completes and the threshold then removes some or
  all of its results
- **THEN** the answer does not say that the search stopped at any bound: the
  threshold removing results is not the search failing to find them

### Requirement: Search is answered from the index, at the depth it is asked for

A search that narrows nothing SHALL be answered from the vector index of the
search model rather than by reading every stored vector. The index's search
effort SHALL be set for each query to at least the depth that query needs — the
page's size, its offset and the one item beyond the page that says whether more
exist — so that a deeper page does not quietly return a worse ranking than a
shallow one, and so that the answer about more items is read rather than
assumed.

A narrowed search SHALL NOT be required to use that index. The narrowing SHALL
be part of what the database plans — a condition of the query, never a filter
applied to a page the database already chose — and which access path answers it
SHALL be the database's own judgement: the vector index, the distances of
exactly the assets the narrowing admits, or, on a corpus small enough for that
to be the cheapest thing to do, the distances of every vector of the search
model. An index able to serve the narrowing on both columns SHALL exist, so that
the choice is a matter of cost rather than of what is possible.

What those ways SHALL share is the meaning of the answer: only assets that
satisfy the narrowing, nearest first with the same tie-break, the same page
bounds, the same threshold behaviour and the same rule for whether more exist.
What they need NOT share is completeness. Only the index is bounded: it MAY stop
before the page is filled, and MUST then say so (above). A path that computes
distances — over the narrowed assets or over all of them — is not bounded and
always says nothing stopped it. So two answers to one question MAY differ in
what they hold, and the one that is short SHALL say why — which is the
difference a client can act on, and the only one it is told.

#### Scenario: The index answers the query
- **WHEN** the execution plan of a search that narrows nothing is inspected
- **THEN** it shows a scan of the search model's vector index and no sequential
  scan of the stored vectors

#### Scenario: A deep page is searched as deeply as it is asked
- **WHEN** a page deep in the ranking is requested
- **THEN** the search effort for that query is at least the size and offset it
  asks for, plus the item beyond them

#### Scenario: The narrowing is a condition of the query, and an index can serve it
- **WHEN** the execution plan of a narrowed search is inspected with sequential
  scans made expensive
- **THEN** it shows the narrowing inside the query rather than above it, and no
  sequential scan of the stored vectors: an index can answer it, whichever path
  the database picks when the costs are its own

#### Scenario: The vector index still answers a narrowed query when it is chosen
- **WHEN** a narrowing broad enough for the database to use the vector index is
  searched with
- **THEN** the index answers it, the narrowing is part of what that scan
  answers, and the page comes back full while matching assets remain

#### Scenario: The same question answered two ways
- **WHEN** one narrowed query is answered by the index within a bound it reaches,
  and the same query is answered by computing the distances exactly
- **THEN** both hold only assets satisfying the narrowing, in the same order,
  and the bounded one may hold fewer — and says that it stopped at its bound,
  which the other never does

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

### Requirement: A search may be narrowed by what an asset carries

The service SHALL accept, on any search, a narrowing by the tags an asset
carries — all of a set, or any of a set — and by top-level equality in its
metadata. The forms SHALL be combinable, and the number of metadata conditions
SHALL be bounded.

A narrowing SHALL be part of the ranking rather than of the page: the answer
SHALL be the nearest assets *that satisfy it*. A page SHALL NOT come back short
merely because the assets nearest the query did not satisfy the narrowing while
matching assets exist further down the ranking — which is what removing rows
from an already chosen page would do.

A narrowing SHALL NOT change what a score means: it decides which assets are
ranked, never how near they are.

A value that is not an acceptable tag, a metadata key outside the accepted
shape, or more metadata conditions than are allowed SHALL be refused with 422
problem details naming what was wrong, and no search SHALL be run.

#### Scenario: A narrowing that matches few assets
- **WHEN** a search is narrowed to a tag that few stored assets carry, and more
  of them exist than a page holds
- **THEN** the page comes back full, with the nearest assets carrying that tag,
  and not shortened by how far down the ranking they sit

#### Scenario: All of a set, and any of a set
- **WHEN** a search is narrowed to assets carrying every tag of one set, and
  again to assets carrying at least one tag of a set
- **THEN** each answer holds exactly the assets that satisfy that condition,
  ranked as they would have been ranked without it

#### Scenario: Narrowing by metadata
- **WHEN** a search is narrowed by a metadata key and value
- **THEN** only assets whose metadata carries that key with that value are
  ranked

#### Scenario: A narrowing nothing satisfies
- **WHEN** a search is narrowed to something no stored asset carries
- **THEN** the answer is an empty page rather than an error

#### Scenario: A narrowing that is not acceptable
- **WHEN** a search is narrowed by a value that is not an acceptable tag, by a
  metadata key outside the accepted shape, or by more metadata conditions than
  are allowed
- **THEN** the answer is 422 problem details naming what was wrong, and no
  search is run

#### Scenario: A score means the same thing narrowed
- **WHEN** the same query is searched with and without a narrowing
- **THEN** an asset that appears in both answers carries the same score in both
