## ADDED Requirements

### Requirement: A query encoder declares the space it answers in

A **query encoder** is an embedder that puts a query into the space of a
storage model rather than into one of its own. It SHALL declare, without
loading anything, the key of the storage model whose vectors its output may be
compared with, and that key SHALL be one the application knows. Its own key
SHALL be distinct from every storage key, so that neither can be mistaken for
the other in configuration, in an answer or in a count.

A query encoder SHALL produce vectors of exactly the width that storage model
declares — checked against the loaded checkpoint, like any other adapter, and
failing the load rather than the query when it does not.

Nothing SHALL ever be stored under a query encoder's key: it takes no place in
the embeddings table, has no index, and is never queued for work. It follows
that enabling one SHALL require no migration and SHALL leave every stored
vector as it was.

#### Scenario: What an encoder declares before loading
- **WHEN** the declaration of an enabled query encoder is read
- **THEN** it names its own key, the storage key whose space it answers in, and
  the width of that space, and nothing has been loaded or fetched

#### Scenario: An encoder pointed at a space that does not exist
- **WHEN** a query encoder declares a storage key the application does not know
- **THEN** the service refuses to start and names both keys

#### Scenario: An encoder whose checkpoint is of the wrong width
- **WHEN** a query encoder's checkpoint produces vectors of a width other than
  the one its storage model declares
- **THEN** loading fails naming the encoder, the storage key and both widths,
  and no vector is returned

#### Scenario: Enabling an encoder changes no stored data
- **WHEN** a build enables a query encoder
- **THEN** no migration is required, no row of the embeddings table changes, and
  the indexing queue receives nothing

### Requirement: A build enables query encoders separately from storage models

The set of query encoders a build runs SHALL come from configuration of its
own, separate from the enabled storage models, and the service SHALL refuse to
start when it names an encoder this build does not implement. An encoder SHALL
be enabled only when the storage model it answers in is enabled too: an encoder
whose space holds nothing has nothing to rank.

Enabling an encoder SHALL NOT change which model answers a search that names no
model: the default stays the storage model it always was.

#### Scenario: An unknown encoder in configuration
- **WHEN** the service is configured with a query encoder key it does not
  implement
- **THEN** it refuses to start and names the offending key

#### Scenario: An encoder whose space is not enabled
- **WHEN** a query encoder is enabled while the storage model it answers in is
  not
- **THEN** the service refuses to start and names both

#### Scenario: The default is unchanged
- **WHEN** a text search names no model and a query encoder is enabled
- **THEN** the search is answered by the default storage model and its own text
  side, exactly as before
