# embedding-models Specification

## Purpose
What every embedding model in the service looks like from the outside: a stable key, a width known before anything is loaded, unit-length vectors, one load per process, and a deterministic stand-in so the rest of the system can be tested without a model.

## Requirements

### Requirement: An embedder declares its identity and width without loading anything
Every embedder SHALL expose a stable model key and the width of the vectors it produces, and both SHALL be readable without loading weights, opening a network connection or reading a cache. The service SHALL take the set of enabled keys from configuration, and SHALL refuse to start when that configuration names a key the service does not implement.

#### Scenario: Width before loading
- **WHEN** the width of an enabled model is read
- **THEN** it equals the width the specification fixes for that key, and nothing has been loaded or fetched

#### Scenario: Unknown key in configuration
- **WHEN** the service is configured with a model key it does not implement
- **THEN** it refuses to start and names the offending key

### Requirement: Vectors are unit length and of the declared width
Every vector an embedder returns SHALL be `float32`, SHALL have exactly the declared width, and SHALL have a Euclidean norm of 1 within floating-point tolerance. This holds for text and for images alike, so cosine similarity is the dot product and the stored vectors of a model are directly comparable.

#### Scenario: Text vector
- **WHEN** an embedder with a text tower embeds a piece of text
- **THEN** the result is one `float32` vector of the declared width whose norm is 1

#### Scenario: Image vector
- **WHEN** an embedder embeds an image
- **THEN** the result is one `float32` vector of the declared width whose norm is 1

#### Scenario: A batch keeps its order
- **WHEN** several inputs are embedded in one call
- **THEN** one vector comes back per input, in the order the inputs were given

### Requirement: An embedder without a text tower refuses text
An embedder that has no text tower SHALL refuse a text request with an error naming the model key, rather than return a vector from another space or an approximation.

#### Scenario: Text asked of an image-only model
- **WHEN** text is embedded with a model that has no text tower
- **THEN** the call fails with an error naming the key, and no vector is returned

### Requirement: A checkpoint that does not fit its key is refused at load
An adapter SHALL compare the width the loaded checkpoint actually produces with the width its key declares, and SHALL fail the load, naming the key and both widths, when they differ. The failure SHALL happen before any vector is returned, so a misconfigured checkpoint cannot reach storage. A declaration-only check elsewhere SHALL NOT be presented as covering this case.

#### Scenario: Checkpoint of the wrong width
- **WHEN** a model key is pointed at a checkpoint whose output width differs from the width the key declares
- **THEN** loading fails with an error naming the key and both widths, and no vector is produced

#### Scenario: Checkpoint that fits
- **WHEN** a model key is pointed at a checkpoint of the declared width
- **THEN** loading succeeds and every vector it returns has that width

### Requirement: A model is loaded at most once per process, and only when needed
Loading SHALL be lazy: importing the application or starting it SHALL load no model, unless the configuration names models to warm up. The first use of a key SHALL load it, and concurrent first uses SHALL load it exactly once and share the result. A load that fails SHALL NOT be remembered as a failure, so a later attempt can succeed.

#### Scenario: Nothing loads at start
- **WHEN** the application starts with no warm-up configured
- **THEN** no model has been loaded and no weights have been fetched

#### Scenario: Concurrent first use
- **WHEN** several callers ask for the same model at the same time before it is loaded
- **THEN** the model is loaded once and every caller receives that same instance

#### Scenario: A failed load can be retried
- **WHEN** a load fails and the same key is requested again
- **THEN** loading is attempted again rather than the earlier failure being replayed

#### Scenario: Deliberate warm-up
- **WHEN** the operator asks for the enabled models to be warmed up
- **THEN** each one is loaded and reported with its key, its width and how long it took

### Requirement: Text longer than the model's context is truncated and the caller is told
When a text input exceeds the model's context length, the embedder SHALL embed the truncated text and SHALL report that truncation happened, so a caller can pass that fact on instead of silently answering a different question.

#### Scenario: Long text
- **WHEN** text longer than the model's context is embedded
- **THEN** a vector comes back and the result states that the input was truncated

#### Scenario: Ordinary text
- **WHEN** text within the model's context is embedded
- **THEN** the result states that nothing was truncated

### Requirement: Neither loading nor inference runs on the event loop
Loading a model and embedding with it SHALL both run on a dedicated, bounded pool of worker threads, not on the thread that serves requests, and the pool's size SHALL be configurable. Loading is the larger of the two — it reads gigabytes from disk or the network — so the asynchronous path SHALL obtain an embedder through that pool as well, and warm-up at start SHALL use the same path.

#### Scenario: The loop keeps running during inference
- **WHEN** an embedding call that takes noticeable time is in flight
- **THEN** other work scheduled on the event loop continues to make progress before it finishes

#### Scenario: The loop keeps running during a load
- **WHEN** a model that takes noticeable time to load is requested through the asynchronous path
- **THEN** other work scheduled on the event loop continues to make progress before the load finishes

### Requirement: A deterministic embedder stands in for the real ones
The service SHALL provide an embedder that produces vectors from its input alone, without weights, a network or a framework runtime, so the rest of the system can be exercised without a model. The same input SHALL always give the same vector; different inputs SHALL give different vectors; and text and an image carrying the same label SHALL land closer to each other than to an unrelated input, so ordering can be tested.

#### Scenario: Same input, same vector
- **WHEN** the deterministic embedder embeds the same input twice, in different processes
- **THEN** both vectors are identical

#### Scenario: Different inputs, different vectors
- **WHEN** it embeds two different inputs
- **THEN** the two vectors differ

#### Scenario: Related text and image
- **WHEN** it embeds a label as text and an image carrying that same label
- **THEN** those two vectors are closer to each other than either is to an unrelated input

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
