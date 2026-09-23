## ADDED Requirements

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

## MODIFIED Requirements

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

Every search SHALL be answered from the vector index of the search model rather
than by reading every stored vector. The index's search effort SHALL be set for
each query to at least the depth that query needs — the page's size, its offset
and the one item beyond the page that says whether more exist — so that a
deeper page does not quietly return a worse ranking than a shallow one, and so
that the answer about more items is read rather than assumed.

A narrowed search SHALL also be answered from that index: the narrowing SHALL be
part of what the index scan answers, not a filter applied to its result. The
service SHALL keep looking, bounded, until the page is filled or that bound is
reached.

#### Scenario: The index answers the query
- **WHEN** the execution plan of a search is inspected
- **THEN** it shows a scan of the search model's vector index and no sequential
  scan of the stored vectors

#### Scenario: A deep page is searched as deeply as it is asked
- **WHEN** a page deep in the ranking is requested
- **THEN** the search effort for that query is at least the size and offset it
  asks for, plus the item beyond them

#### Scenario: The index answers a narrowed query too
- **WHEN** the execution plan of a narrowed search is inspected
- **THEN** it shows a scan of the same vector index, with the narrowing inside
  what that scan answers, and no sequential scan of the stored vectors
