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

### Requirement: A model key earns its place by measurement

A model key is permanent: it is part of an embedding's identity, it takes a
value in the schema's allowlist, it costs an index and a vector for every asset
the service holds, and it queues work for every upload. So before a key is
added, this repository SHALL publish what that model answers **that the keys
already present do not**, and SHALL do it as a measurement rather than as a
description.

The comparison SHALL cover **every key the service already stores vectors of
that kind under**, not a key chosen for the comparison: a candidate that beats
one incumbent and duplicates another has not answered the question.

The measurement SHALL be produced by a command in the repository, over a corpus
the command builds or names, so that anyone can re-run it and get the same
answer. Its bound SHALL be fixed before the numbers are seen, and SHALL be
about the margin over the best of those keys — a key that is only marginally
better than an existing one at the same question has not earned a migration.

The number the bound is read on SHALL be one that a model's own similarity scale
cannot move. Models differ in how widely they spread cosine similarity, so a
statistic built from the size of the scores can rank a candidate above an
incumbent that in fact orders results the other way round. A statistic about the
**order** a model puts candidates in survives that; any other number may be
published beside it, as a diagnostic that decides nothing.

A candidate that does not clear the bound SHALL NOT be added, and the
measurement SHALL be published anyway, in the record that decided it. "Not
added" is an outcome of the same standing as "added": what this requirement
forbids is a key whose value nobody measured.

This requirement is about keys the service **stores** vectors under. It does
not govern a query encoder, which stores nothing and whose own claim —
answering in another key's space — is measured under the rule it already has.

#### Scenario: A candidate that answers something new
- **WHEN** a model is proposed as a new key and a published measurement shows
  it clears the stated margin over every key the service already runs
- **THEN** the key may be added, and the record that admits it cites the
  measurement and the command that produced it

#### Scenario: A statistic a model's own scale can move
- **WHEN** the candidate is ranked above an incumbent by a statistic computed
  from how large the similarity scores are, rather than from the order they put
  results in
- **THEN** that statistic does not decide: the bound is read on a number that
  survives rescaling, and the record publishes both and says which one decided

#### Scenario: A candidate that duplicates a key already present
- **WHEN** the measurement shows the candidate does not clear the margin
- **THEN** the key is not added, and the numbers are published in the record
  that refused it, so the question does not have to be asked again from nothing

#### Scenario: The measurement can be re-run
- **WHEN** somebody re-runs the published command against the corpus it names
- **THEN** the command rebuilds the corpus from that folder by itself, needing
  no download and no labelling, and publishes a digest over the corpus's file
  names and bytes, so a reader can establish that two runs measured the same
  pictures

#### Scenario: An input the repository does not pin
- **WHEN** the measurement loads a checkpoint whose revision this repository
  does not fix — a name a deployment configures rather than a pinned commit
- **THEN** the record SHALL say so, and SHALL NOT present any identity it prints
  for that checkpoint as establishing which weights answered: reproducibility is
  claimed only for the inputs this repository pins, and the rest are named as
  the open question they are

### Requirement: A checkpoint is loaded at an immutable revision

A model key is part of an embedding's identity, so what the key names has to be
fixed. A checkpoint **name** is not fixed: it is configuration, it points at
whatever a repository holds today, and two loads a month apart can answer with
different weights under the same key.

Every storage model SHALL therefore be loadable at an explicit revision, and
that revision SHALL be configuration with a default this repository has verified
— configuration, because §2.3 requires a compatible checkpoint (a fine-tune, a
mirror) to be substitutable without a schema change, and defaulted, because a
deployment that configures nothing SHALL still be reproducible.

**A revision SHALL be an immutable commit identifier**: a full 40-character
hexadecimal commit. A branch or a tag is a name for a moving target, which the
model hub accepts and which would leave the defect exactly where it was. The
service SHALL refuse to start when a configured revision is anything else, and
SHALL name the setting.

**When a load has a revision**, that revision SHALL be resolved once and used
for **every** artefact the adapter reads — the weights and the processor alike.
An adapter that resolves them separately can pair weights from one snapshot with
preprocessing from another, which no width check and no tensor check can see.
A load that has no revision, which is the case below, makes no such promise: it
behaves as every load behaved before this requirement existed.

A revision belongs to the repository it is a commit of. When a checkpoint name
is configured away from its default and no revision is configured with it, the
default revision SHALL NOT be applied to it: that commit belongs to a repository
that was replaced. Such a checkpoint SHALL be loaded as it was loaded before
this rule existed — without a revision — and the service SHALL say so where an
operator can see it, and SHALL NOT refuse to start. A configuration that the
service accepted before SHALL keep working.

#### Scenario: A model is loaded at its default revision
- **WHEN** a build enables a storage model, leaves its checkpoint name at the
  default and configures no revision for it
- **THEN** the adapter loads every artefact of that checkpoint at the revision
  this repository verified, and the same load a year later reads the same
  weights

#### Scenario: A revision that names a moving target
- **WHEN** a revision is configured as a branch, a tag, an abbreviated commit or
  an empty value
- **THEN** the service refuses to start and names the setting, because such a
  revision would resolve to whatever the repository holds at load time

#### Scenario: The weights and the preprocessing come from one snapshot
- **WHEN** an adapter reads a checkpoint's weights and its processor **and the
  load has a revision**
- **THEN** both are read at that one revision, so they cannot come from
  different snapshots

#### Scenario: A substituted checkpoint with no revision of its own
- **WHEN** a checkpoint name is configured away from its default and no revision
  is configured with it — for either storage model
- **THEN** the service starts, that adapter loads the checkpoint **without a
  revision**, exactly as every adapter did before this requirement existed, and
  the service states that the checkpoint is unpinned. The default revision,
  which is a commit of the repository that was replaced, is not applied to it,
  and the one-snapshot guarantee above does not apply to that load
