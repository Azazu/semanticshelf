## ADDED Requirements

### Requirement: The tags in use are listable with their counts

The service SHALL answer, in one request, which tags are in use and how many
assets carry each, ordered by count with the most used first and ties broken by
the tag itself so that the list is stable. The number of tags returned SHALL be
bounded, with a default and a maximum, and a request beyond the maximum SHALL
be refused with 422 problem details naming the parameter.

A tag that no asset carries SHALL NOT appear, and a store with no tags SHALL be
answered with an empty list rather than an error.

#### Scenario: Tags in use
- **WHEN** the tags are requested while assets carry them
- **THEN** each tag in use comes back with the number of assets carrying it,
  most used first

#### Scenario: Two tags used equally often
- **WHEN** two tags are carried by the same number of assets
- **THEN** their order is decided by the tags themselves, and is the same in
  every request

#### Scenario: A tag no asset carries any more
- **WHEN** the last asset carrying a tag is deleted and the tags are requested
- **THEN** that tag is absent from the answer

#### Scenario: A bound beyond the maximum
- **WHEN** more tags are requested than the maximum allows
- **THEN** the answer is 422 problem details naming the parameter
