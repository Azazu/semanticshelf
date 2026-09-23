## ADDED Requirements

### Requirement: The interface can ask with a picture

The interface SHALL let a person search with a picture: one they choose from
their machine, and one already in the store, reached from any picture the
interface shows. It SHALL show the results as the search page shows them — the
pictures, their scores, the model that ranked them, and the same way of asking
for more.

A picture that the service refuses, and an asset the service has no vector for,
SHALL be reported as the service worded it, leaving the page usable.

#### Scenario: A picture from the person's machine
- **WHEN** a person searches with a picture they chose
- **THEN** the pictures the service found come back with their scores and the
  model that ranked them

#### Scenario: More like this one
- **WHEN** a person asks, from a picture the interface is showing, for the ones
  that look like it
- **THEN** the service is asked for that asset's neighbours, and the asset
  itself is not among what comes back

#### Scenario: An asset the service cannot answer for
- **WHEN** a person asks for the neighbours of an asset that has no vector for
  the search model yet
- **THEN** the page shows the service's own refusal, and stays usable
