## Purpose

What every embedding model in the service looks like from the outside: a stable key, a width known before anything is loaded, unit-length vectors, one load per process, and a deterministic stand-in so the rest of the system can be tested without a model.

## ADDED Requirements

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

### Requirement: Inference never runs on the event loop
Embedding SHALL run on a dedicated, bounded pool of worker threads, not on the thread that serves requests, and the pool's size SHALL be configurable. While an embedding call is in flight the service SHALL keep answering.

#### Scenario: The loop keeps running
- **WHEN** an embedding call that takes noticeable time is in flight
- **THEN** other work scheduled on the event loop continues to make progress before it finishes

### Requirement: A deterministic embedder stands in for the real ones
The service SHALL provide an embedder that produces vectors from its input alone, without weights, a network or a framework runtime, so the rest of the system can be exercised without a model. The same input SHALL always give the same vector; different inputs SHALL give different vectors; and text and an image carrying the same token SHALL land closer to each other than to an unrelated input, so ordering can be tested.

#### Scenario: Same input, same vector
- **WHEN** the deterministic embedder embeds the same input twice, in different processes
- **THEN** both vectors are identical

#### Scenario: Different inputs, different vectors
- **WHEN** it embeds two different inputs
- **THEN** the two vectors differ

#### Scenario: Related text and image
- **WHEN** it embeds a token as text and an image carrying that same token
- **THEN** those two vectors are closer to each other than either is to an unrelated input
