## MODIFIED Requirements

### Requirement: Listing is bounded, ordered and stable

The service SHALL list assets newest first, with a deterministic tie-break, so
that two pages of the same listing cannot show the same asset twice or miss
one. The page size SHALL have a default and a maximum, and the offset SHALL
have a maximum. The response SHALL carry the items, the page size, the offset
and whether more items exist, and SHALL NOT carry a total count. Listing SHALL
support filtering by tags — all of a set, or any of a set — by top-level
equality in an asset's metadata, by source, and by the state of the newest work
for a named model.

The metadata filter SHALL accept the same conditions a search accepts, in the
same number and of the same shape, so that a person narrowing a listing and a
person narrowing a search write the same thing.

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

#### Scenario: Filtering by metadata
- **WHEN** assets are listed with a filter naming a metadata key and value
- **THEN** exactly the assets whose metadata carries that key with that value
  come back

#### Scenario: Filtering by the state of the work
- **WHEN** assets are listed with a filter naming a model and a state
- **THEN** exactly the assets whose newest work for that model is in that
  state come back

#### Scenario: A filter that names something unknown
- **WHEN** the filter names a model the service does not know, or a state that
  does not exist
- **THEN** the answer is 422 problem details naming the value

#### Scenario: A metadata filter that is not acceptable
- **WHEN** the filter names a metadata key outside the accepted shape, or more
  conditions than are allowed
- **THEN** the answer is 422 problem details naming what was wrong
