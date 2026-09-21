## MODIFIED Requirements

### Requirement: An asset is readable by its identifier

The service SHALL answer a request for an existing asset with its
representation, and a request for an identifier that is not stored with 404
problem details. The representation SHALL carry the asset's identifier, when
it was created, its detected content type, its dimensions, its size in bytes,
its content hash, the original filename it arrived with, its source, its tags,
its metadata, the state of its indexing work per model, and links to its bytes
and its thumbnail.

#### Scenario: An asset that exists
- **WHEN** an existing asset is requested by identifier
- **THEN** the answer is 200 with its representation, including links to its
  bytes and its thumbnail

#### Scenario: An identifier that is not stored
- **WHEN** an asset is requested by an identifier no asset carries
- **THEN** the answer is 404 problem details

#### Scenario: The state of the work is part of the asset
- **WHEN** an asset whose work is partly done is read
- **THEN** its representation names each model with the state of that model's
  newest work

### Requirement: Listing is bounded, ordered and stable

The service SHALL list assets newest first, with a deterministic tie-break, so
that two pages of the same listing cannot show the same asset twice or miss
one. The page size SHALL have a default and a maximum, and the offset SHALL
have a maximum. The response SHALL carry the items, the page size, the offset
and whether more items exist, and SHALL NOT carry a total count. Listing SHALL
support filtering by tags — all of a set, or any of a set — by source, and by
the state of the newest work for a named model.

#### Scenario: Paging through assets
- **WHEN** assets are listed page by page
- **THEN** each asset appears exactly once across the pages, newest first

#### Scenario: More items exist
- **WHEN** a page is requested and more assets exist beyond it
- **THEN** the response says so, and it carries no total count

#### Scenario: A page size over the maximum
- **WHEN** a page size beyond the maximum is requested
- **THEN** the answer is 422 problem details naming the parameter

#### Scenario: Filtering by tags
- **WHEN** assets are listed with a filter requiring all of several tags, and
  again with a filter requiring any of them
- **THEN** each answer contains exactly the assets that satisfy that filter

#### Scenario: Filtering by the state of the work
- **WHEN** assets are listed with a filter naming a model and a state
- **THEN** exactly the assets whose newest work for that model is in that
  state come back

#### Scenario: A filter that names something unknown
- **WHEN** the filter names a model the service does not know, or a state that
  does not exist
- **THEN** the answer is 422 problem details naming the value
