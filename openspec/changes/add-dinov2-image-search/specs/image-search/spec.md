## Purpose

Asking with a picture instead of words: a picture sent in a request, or one the
store already holds, and the pictures nearest to it — what is refused, what is
never kept, and how the answer relates to the one words give.

## ADDED Requirements

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
maximum page, the same searchable depth, the same threshold behaviour, the same
order and the same promise about a page whose edge cuts a group of identical
scores.

#### Scenario: The same envelope
- **WHEN** a picture query and a text query are both answered
- **THEN** their answers have the same shape, and differ only in the values

#### Scenario: The same bounds
- **WHEN** a picture query asks for a page beyond the searchable depth, or a
  page larger than the maximum
- **THEN** it is refused exactly as a text query asking for the same is

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
