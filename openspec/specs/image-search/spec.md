# image-search Specification

## Purpose
Asking with a picture instead of words: a picture sent in a request, or one the
store already holds, and the pictures nearest to it — what is refused, what is
never kept, and how the answer relates to the one words give.

## Requirements

### Requirement: A picture sent as a query is answered and not kept

The service SHALL accept a picture in a request and answer it with the stored
assets whose vectors of the search model are nearest to that picture's vector,
closest first. The picture SHALL be accepted only under the rules an uploaded
picture is accepted by — the same formats decided from the bytes, the same size
and dimension bounds — and refused with the same problem details when it is not.

The picture SHALL NOT be stored: no asset SHALL be created for it, nothing
SHALL be written under the media root that outlives the request, and no trace
of it SHALL remain after the answer.

#### Scenario: A picture finds what looks like it
- **WHEN** a picture is searched with and the store holds assets whose vectors
  of the search model are near it
- **THEN** those assets come back ordered from nearest to furthest, and the
  answer names the model that ranked them

#### Scenario: The query picture leaves nothing behind
- **WHEN** a picture is searched with
- **THEN** no asset exists for it afterwards, and nothing of it remains under
  the media root

#### Scenario: Something that is not an acceptable picture
- **WHEN** the request carries bytes that do not decode as a picture the
  service accepts, or one outside the bounds an upload enforces
- **THEN** the answer is the same problem details an upload gives for it, and
  nothing is searched

#### Scenario: A store with nothing indexed for that model
- **WHEN** a picture is searched with and no asset has a vector for the search
  model
- **THEN** the answer is an empty page rather than an error

### Requirement: An asset can ask for what looks like it

The service SHALL answer, for a stored asset, the other assets whose vectors of
the search model are nearest to that asset's own vector. It SHALL use the
vector already stored rather than computing one again, and SHALL NOT include
the asset itself in the answer — at any page of it.

The pages of that answer SHALL be pages of the ranking the asset has already
been taken out of: removing it SHALL NOT, by itself, make a neighbour appear on
two consecutive pages, drop one between them, or leave a full page short of what
it asked for. What an approximate index promises about pages is otherwise
unchanged and inherited whole (`text-search`: for a store that has not changed
and a page across which no group of identical scores falls, two requests return
the same items; where such a group is cut by a page's edge, nothing is promised
about which of its members that page holds).

An asset that has no vector for the search model SHALL be refused with 409
problem details naming that, rather than answered with an empty page: nothing
is known about what it looks like, which is not the same as nothing being like
it.

#### Scenario: An asset finds its neighbours
- **WHEN** the neighbours of a stored asset are asked for and it has a vector
  for the search model
- **THEN** the nearest other assets come back, ordered, and no model is loaded
  to answer

#### Scenario: The asset itself is never its own neighbour
- **WHEN** the neighbours of an asset are asked for, on any page
- **THEN** it does not appear among them

#### Scenario: One page after another
- **WHEN** the neighbours of an asset are read page after page over a store that
  has not changed, and no group of identical scores falls across any of those
  pages' edges
- **THEN** each neighbour appears on exactly one of those pages, in ranking
  order, and every page but the last carries as many as it asked for

#### Scenario: A page of neighbours whose edge cuts a group of identical scores
- **WHEN** such a group is cut by the edge of a page of an asset's neighbours
- **THEN** the promise is the one the search surface already makes about that
  case, no weaker and no stronger, and the asset itself is still absent

#### Scenario: An asset that has no vector yet
- **WHEN** the neighbours of an asset whose work for the search model has not
  produced a vector are asked for
- **THEN** the answer is 409 problem details naming that, and nothing is
  searched

#### Scenario: An asset that does not exist
- **WHEN** the neighbours of an identifier no asset carries are asked for
- **THEN** the answer is 404 problem details

### Requirement: A picture query answers in the shape a text query answers in

An answer to a picture SHALL carry what an answer to words carries: the items
with their assets and scores, the page's size and offset, whether more exist,
and the model that ranked them. The bounds SHALL be the same bounds — the same
maximum page, the same threshold behaviour, the same order and the same promise
about a page whose edge cuts a group of identical scores.

The searchable depth SHALL be the same for a picture sent as a query. For an
answer that excludes an asset from its own neighbours it SHALL be one page
shallower, because the excluded asset is itself one of the candidates the index
is allowed to produce and the row beyond the page is another; that limit SHALL
be a stated bound, refused like any other page beyond the searchable depth, and
SHALL NOT be met by answering from a shallower search than the page needs.

#### Scenario: The same envelope
- **WHEN** a picture query and a text query are both answered
- **THEN** their answers have the same shape, and differ only in the values

#### Scenario: The same bounds
- **WHEN** a picture query asks for a page beyond the searchable depth, or a
  page larger than the maximum
- **THEN** it is refused exactly as a text query asking for the same is

#### Scenario: The deepest page an asset's neighbours can reach
- **WHEN** the neighbours of an asset are asked for at the deepest page that
  bound allows, and then at one page deeper
- **THEN** the first is answered, with whether more exist still exact, and the
  second is refused as a page beyond the searchable depth

### Requirement: A picture query is answered by the model it names

Which model answers a picture query, and what happens when it cannot, SHALL be
the rule the search surface already carries (`text-search`: a search names the
model it used, may be asked for a particular one, and refuses a model this build
does not run or one that cannot take that kind of query). A picture query SHALL
be answerable only by a model with an image side.

The picture SHALL be embedded by the same model whose stored vectors are
searched, so a score between vectors of different models cannot arise.

#### Scenario: A model that cannot look at pictures
- **WHEN** a picture query names a model with no image side
- **THEN** it is refused as the search surface refuses a model that cannot take
  the kind of query it was given, and nothing is searched

#### Scenario: Vectors of another model are never mixed in
- **WHEN** assets carry vectors under more than one model and a picture query
  names one of them
- **THEN** only that model's vectors are ranked, and the picture is embedded by
  that same model

### Requirement: A picture query may be narrowed the same way words are

Both ways of asking with a picture — one sent in a request and one the store
already holds — SHALL accept the same narrowing a text query accepts, and SHALL
be bound by the same rule (`text-search`: the narrowing is part of the ranking
rather than of the page, it never changes what a score means, an unacceptable
one is refused, and a search that stops at its bound says so).

For an asset asking about itself, the narrowing SHALL apply to its neighbours
and never to the asset itself: an asset SHALL be able to ask what looks like it
among a narrower set even when it does not satisfy that narrowing.

#### Scenario: A picture search narrowed by tags
- **WHEN** a picture is searched with and the search is narrowed to a tag
- **THEN** only assets carrying that tag are ranked, nearest first, and a page
  is not shortened by assets that were excluded

#### Scenario: An asset's neighbours narrowed
- **WHEN** the neighbours of an asset are asked for with a narrowing
- **THEN** only assets satisfying it come back, and the asset itself is absent
  as it always is

#### Scenario: An asset that does not satisfy its own narrowing
- **WHEN** an asset whose tags do not satisfy the narrowing asks for its
  neighbours under it
- **THEN** it is still answered: the narrowing decides which neighbours are
  ranked, not whether the question may be asked
