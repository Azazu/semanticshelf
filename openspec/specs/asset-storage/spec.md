# asset-storage Specification

## Purpose
The durable record of an indexed image: what makes two assets the same, which field values the store accepts at all, how tags and metadata stay queryable, and what disappears when an asset is removed.

## Requirements

### Requirement: An asset is identified by its content
The store SHALL keep at most one asset per content hash. A second record carrying a hash that is already stored SHALL be rejected by the store itself, not only by the code that calls it, so two callers racing on the same bytes cannot both succeed.

#### Scenario: Same bytes stored twice
- **WHEN** a record is added whose content hash already exists
- **THEN** the write is rejected and the stored record is left unchanged

#### Scenario: Different bytes
- **WHEN** two records with different content hashes are added
- **THEN** both are stored and each keeps its own identity

### Requirement: Field domains are enforced by the store
The store SHALL reject an asset whose content type is outside `image/jpeg`, `image/png`, `image/webp`; whose file extension is outside `jpg`, `png`, `webp`; whose source is outside `upload`, `folder`; or whose width, height or byte size is not positive. Enforcement lives with the data, so a record that never passed the upload path cannot be malformed either.

#### Scenario: Unsupported content type
- **WHEN** a record is added with a content type outside the allowed set
- **THEN** the write is rejected

#### Scenario: Non-positive dimensions
- **WHEN** a record is added with a width, height or size of zero or less
- **THEN** the write is rejected

### Requirement: Tags and metadata are stored queryably
An asset SHALL carry a list of tags and a JSON metadata object, both optional and both empty by default. The store SHALL answer containment queries over each of them — every listed tag present, at least one listed tag present, a metadata object containing given keys and values — without reading every asset.

#### Scenario: Filter by tags
- **WHEN** assets are queried for a tag they carry
- **THEN** exactly the assets carrying that tag are returned

#### Scenario: Filter by metadata
- **WHEN** assets are queried for a metadata key and value they carry
- **THEN** exactly the assets whose metadata contains that pair are returned

#### Scenario: An index answers each containment query
- **WHEN** the execution plan of a tag query and of a metadata query is inspected with sequential scans made expensive
- **THEN** each plan reaches its index rather than reading the table

### Requirement: Removing an asset removes everything derived from it
Removing an asset SHALL remove, in the same transaction, every embedding and every indexing job that belongs to it. No derived row SHALL ever refer to an asset that is gone.

#### Scenario: Asset with embeddings and jobs is removed
- **WHEN** an asset that has embeddings and indexing jobs is removed
- **THEN** the asset, its embeddings and its jobs are all gone once the transaction commits

#### Scenario: Derived row cannot outlive its asset
- **WHEN** an embedding or a job is written for an asset id that does not exist
- **THEN** the write is rejected
