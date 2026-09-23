## MODIFIED Requirements

### Requirement: Search shows what was found and how well

The search page SHALL take a description, ask the service for it, and show the
pictures it found with the score the service gave each one. It SHALL offer the
threshold the API offers and a way to ask for the next page of results, which
SHALL use the offset the API takes rather than fetching more and hiding some.

It SHALL also offer a filter by tag, and that filter SHALL be the service's own:
it SHALL travel with the search rather than remove rows from what was already
fetched, so a narrowed search returns the nearest pictures that carry the tag
however deep in the ranking they sit.

The page SHALL say when a search found nothing, and SHALL say which model
answered, because a score means nothing without it. When the service reports
that it stopped at its own bound before filling a page, the page SHALL say so
rather than present the result as the end of the ranking.

#### Scenario: A description that finds pictures
- **WHEN** a person searches for something the corpus holds
- **THEN** the pictures come back in the service's order, each with its score,
  and the model that ranked them is named

#### Scenario: Asking for more
- **WHEN** a person asks for more results
- **THEN** the next page is requested from the service by offset, and what was
  already shown does not change

#### Scenario: A search that finds nothing
- **WHEN** a search returns no results, or the threshold removes them all
- **THEN** the page says so plainly rather than showing an empty grid

#### Scenario: A tag that nothing fetched so far carries
- **WHEN** a search narrowed by a tag comes back empty because nothing the
  service reached carries it
- **THEN** the page says that the narrowing is what emptied it, and says
  whether the service stopped at its own bound rather than at the end of the
  ranking — the caveat that the filter applied only to what had been fetched is
  gone, because it no longer does

#### Scenario: A search narrowed by a tag
- **WHEN** a person searches with a tag chosen
- **THEN** the tag is part of what the service is asked, and the pictures that
  come back are the nearest ones carrying it

#### Scenario: A narrowed search the service could not finish
- **WHEN** the service reports that it stopped at its bound before filling the
  page
- **THEN** the page says that there may be more matches further down, rather
  than showing a short page as the whole answer
