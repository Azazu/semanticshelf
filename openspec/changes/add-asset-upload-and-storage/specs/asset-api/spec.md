## Purpose

The resource surface of an asset once it exists: reading its representation,
serving its bytes and its thumbnail, listing assets with filters, changing the
parts of an asset that are allowed to change, and removing it.

## ADDED Requirements

### Requirement: An asset is readable by its identifier

The service SHALL answer a request for an existing asset with its
representation, and a request for an identifier that is not stored with 404
problem details. The representation SHALL carry the asset's identifier, when
it was created, its detected content type, its dimensions, its size in bytes,
its content hash, the original filename it arrived with, its source, its tags,
its metadata, and links to its bytes and its thumbnail.

#### Scenario: An asset that exists
- **WHEN** an existing asset is requested by identifier
- **THEN** the answer is 200 with its representation, including links to its
  bytes and its thumbnail

#### Scenario: An identifier that is not stored
- **WHEN** an asset is requested by an identifier no asset carries
- **THEN** the answer is 404 problem details

### Requirement: Bytes are streamed with their content type and validators

The service SHALL serve an asset's original bytes with the content type it
detected at upload, and its thumbnail with the thumbnail's own type. Both
SHALL be streamed from storage rather than read into memory, and both SHALL
carry a cache lifetime marked private and an entity tag derived from the
content hash, so a client can revalidate. An asset whose file is missing from
storage SHALL answer 404 with a warning recorded in the log, never a server
error.

#### Scenario: The original bytes
- **WHEN** an asset's bytes are requested
- **THEN** the answer is 200 with the detected content type, an entity tag
  derived from the content hash, and a private cache lifetime

#### Scenario: The thumbnail
- **WHEN** an asset's thumbnail is requested
- **THEN** the answer is 200 with the thumbnail's content type and the same
  caching and validator rules

#### Scenario: A file that is gone
- **WHEN** the bytes of an asset whose file is missing from storage are
  requested
- **THEN** the answer is 404 problem details and the loss is recorded in the
  log as a warning

#### Scenario: A large picture is served
- **WHEN** a picture larger than a comfortable buffer is served
- **THEN** it reaches the client without being held in memory in full

### Requirement: Listing is bounded, ordered and stable

The service SHALL list assets newest first, with a deterministic tie-break, so
that two pages of the same listing cannot show the same asset twice or miss
one. The page size SHALL have a default and a maximum, and the offset SHALL
have a maximum. The response SHALL carry the items, the page size, the offset
and whether more items exist, and SHALL NOT carry a total count. Listing SHALL
support filtering by tags — all of a set, or any of a set — and by source.

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

### Requirement: Tags and metadata can change, the picture cannot

The service SHALL accept a partial update of an asset's tags and metadata,
where an omitted field is left untouched and an explicit null clears the
metadata. The same normalisation and the same limits as at upload SHALL apply.
The stored bytes, the content hash, the dimensions and the content type SHALL
NOT be changeable through any endpoint.

#### Scenario: Only the tags are given
- **WHEN** an update carries tags and no metadata
- **THEN** the tags are replaced by the normalised set and the metadata is
  unchanged

#### Scenario: Metadata is cleared
- **WHEN** an update sets metadata explicitly to null
- **THEN** the asset's metadata becomes empty and its tags are unchanged

#### Scenario: An attempt to change the picture
- **WHEN** an update tries to change the content hash, the dimensions or the
  content type
- **THEN** those values are unchanged

#### Scenario: An invalid tag in an update
- **WHEN** an update carries a tag that does not satisfy the tag rules
- **THEN** the answer is 422 problem details naming the value, and the asset
  is unchanged

### Requirement: Deleting an asset removes everything derived from it

Deleting an asset SHALL remove its row together with its embeddings and its
indexing work in one transaction, and SHALL remove its files after that
transaction commits. A failure to remove a file SHALL be recorded as a warning
and left to the prune command rather than failing the request. Deleting an
asset that is not stored SHALL answer 404: the second caller is told it does
not exist.

#### Scenario: An asset is deleted
- **WHEN** an existing asset is deleted
- **THEN** the answer is 204, its row and everything derived from it are gone,
  and neither of its files remains

#### Scenario: The same asset is deleted twice
- **WHEN** a delete is repeated for the same asset
- **THEN** the second answer is 404 problem details

#### Scenario: A file cannot be removed
- **WHEN** an asset's row is deleted but one of its files cannot be removed
- **THEN** the request still succeeds, the loss is recorded as a warning, and
  the file is reported by the prune command as an orphan
