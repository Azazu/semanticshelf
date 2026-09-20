## Purpose

The durable side of semantic search: one vector per asset and model, a dimension the store itself guarantees, and a nearest-neighbour lookup that is answered from an index and never compares vectors produced by different models.

## ADDED Requirements

### Requirement: An embedding is identified by its asset and its model
The store SHALL keep at most one embedding per pair of asset and model key. Writing an embedding for a pair that already exists SHALL replace the stored vector rather than add a second row, so re-extracting after a delivery retry leaves exactly one vector.

#### Scenario: Re-extraction of the same pair
- **WHEN** an embedding is written twice for the same asset and model
- **THEN** one row remains and it holds the vector written last

#### Scenario: Two models for one asset
- **WHEN** embeddings are written for one asset under two different model keys
- **THEN** both are stored and neither replaces the other

### Requirement: The dimension of a vector is fixed per model and enforced by the store
Every model key SHALL have one declared dimension. The store SHALL reject a vector whose dimension differs from the dimension declared for its model key, and SHALL reject a model key it does not know. The application SHALL declare the same keys and dimensions, and a mismatch between the application's declaration and the store's SHALL fail the build's checks rather than surface at runtime.

#### Scenario: Wrong dimension for a known model
- **WHEN** a vector whose dimension differs from the model's declared dimension is written
- **THEN** the write is rejected by the store

#### Scenario: Unknown model key
- **WHEN** an embedding is written under a model key the store does not know
- **THEN** the write is rejected by the store

#### Scenario: Declarations drift apart
- **WHEN** the application declares a model key or a dimension the store does not
- **THEN** a check fails and names the difference

### Requirement: Nearest-neighbour lookup is per model and index-backed
A nearest-neighbour lookup SHALL take a model key and a query vector of that model's dimension, and SHALL return the stored assets of that model ordered by ascending cosine distance, closest first, limited to the requested count. Vectors stored under another model key SHALL never appear in the result. The lookup SHALL be answered from an index built for that model; it MUST NOT read every row of the store.

#### Scenario: Ordering
- **WHEN** a lookup runs for a model whose vectors are stored
- **THEN** the results are that model's assets ordered by ascending cosine distance to the query vector

#### Scenario: Model isolation
- **WHEN** vectors of two models are stored and a lookup runs for one of them
- **THEN** no asset appears in the result by virtue of the other model's vector, even when the two dimensions are equal

#### Scenario: The index answers the query
- **WHEN** the execution plan of the lookup is inspected
- **THEN** it shows a scan of that model's vector index and no sequential scan of the embeddings store
