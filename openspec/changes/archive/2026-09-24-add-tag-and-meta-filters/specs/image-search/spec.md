## ADDED Requirements

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
