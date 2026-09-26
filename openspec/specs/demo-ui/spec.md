# demo-ui Specification

## Purpose
The face of the service: what the demonstration interface may talk to, what its
pages promise the person using them, how a refusal reaches that person, and what
the interface is forbidden to know.

## Requirements

### Requirement: The interface is a client of the service and nothing else

The interface SHALL reach the service only over its HTTP API. It SHALL NOT open
the database, SHALL NOT read or write the media root, SHALL NOT load an
embedding model, and SHALL NOT import the service's own code. Every picture it
displays SHALL be fetched from an address the API gave it.

It SHALL be configured by the address of the service: the address the interface
itself calls, and — where a browser cannot use that one — the address the
pictures are given to the browser under. The second SHALL default to the first,
so a deployment where they are the same is configured by one setting, and the
interface SHALL NOT invent either of them from anything but configuration.

Both SHALL have defaults that match the documented development port.

#### Scenario: The interface does not import the service
- **WHEN** the interface's own modules are read, including the imports inside
  their functions
- **THEN** none of them imports the service's code — which is what a check can
  answer; that the interface opens no database, reads no media root and loads no
  model is held by there being nothing in it that could, and by review of these
  few modules

#### Scenario: Where a picture comes from
- **WHEN** the interface shows any picture
- **THEN** it is addressed by a URL the API returned, and the interface never
  reads the bytes itself

#### Scenario: A service somewhere else
- **WHEN** the interface is told a different address for the service
- **THEN** it talks to that one, and nothing else about it changes

#### Scenario: The interface's server and the browser are on different networks
- **WHEN** the interface is told one address to call and another for the
  pictures — the case a container stack creates, where the service's name
  resolves for the interface's server and not for the browser
- **THEN** its own requests go to the first and every picture it shows is
  addressed by the second

#### Scenario: One address is enough when one address is true
- **WHEN** the interface is told only the address it calls
- **THEN** the pictures are addressed by that same one, and nothing about the
  configuration got harder

#### Scenario: The service is not answering
- **WHEN** the service cannot be reached at all
- **THEN** the page says so in a sentence a person can act on, and the
  interface stays usable rather than failing with a stack trace

### Requirement: A refusal is shown as the service worded it

When the service refuses something, the interface SHALL show that refusal as
the service explained it — the title and the detail of the problem it returned —
and SHALL NOT show a stack trace, a bare status code, or its own invented
wording. A refusal SHALL leave the rest of the page usable.

#### Scenario: An upload the service refuses
- **WHEN** a person uploads something the service refuses
- **THEN** the page shows the service's own title and detail for that refusal,
  and the person can try another file without reloading anything

#### Scenario: A search the service refuses
- **WHEN** a person asks for something the service refuses, such as a query
  beyond its bound
- **THEN** the page shows that refusal in the same way, and the previous
  results are not replaced by an error

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

### Requirement: Browsing shows the corpus and what is known about a picture

The browse page SHALL show the stored pictures a page at a time, SHALL offer the
tags in use as a way to narrow them, and SHALL show, for a chosen picture, what
the service knows about it: its metadata, its indexing state per model, and the
picture itself at full size.

Deleting a picture SHALL be possible from that view and SHALL require a
confirmation first. After a deletion the page SHALL reflect the store as it now
is.

#### Scenario: Narrowing by a tag
- **WHEN** a person picks a tag from the tags in use
- **THEN** the grid shows the pictures carrying it, and says how it was narrowed

#### Scenario: Looking at one picture
- **WHEN** a person opens a picture from the grid
- **THEN** they see its metadata, its indexing state per model and the full-size
  picture, all as the service reports them

#### Scenario: Deleting a picture
- **WHEN** a person deletes a picture
- **THEN** it is deleted only after a confirmation, and afterwards the page no
  longer shows it

### Requirement: Uploading and the state of the service are visible

The interface SHALL let a person add a picture with tags and metadata, and SHALL
report what the service made of it. It SHALL also show whether the service is
ready, how much it holds, how much indexing work is in each state and how long
the oldest waiting work has been waiting.

#### Scenario: Adding a picture
- **WHEN** a person uploads a picture with tags and metadata
- **THEN** the service's answer is shown — the asset it created, or its refusal
  worded as the service worded it

#### Scenario: Reading the state
- **WHEN** a person opens the status page
- **THEN** it shows whether the service is ready, what it holds, the work per
  model and state, and the age of the oldest waiting work, or says plainly that
  nothing is waiting
