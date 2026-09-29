## ADDED Requirements

### Requirement: A checkpoint is loaded at a revision, not at a name

A model key is part of an embedding's identity, so what the key names has to be
fixed. A checkpoint **name** is not fixed: it is configuration, it points at
whatever a repository holds today, and two loads a month apart can answer with
different weights under the same key.

Every storage model SHALL therefore be loaded at an explicit revision, and that
revision SHALL be configuration with a default this repository has verified —
configuration, because §2.3 requires a compatible checkpoint (a fine-tune, a
mirror) to be substitutable without a schema change, and defaulted, because a
deployment that configures nothing SHALL still be reproducible.

The revision SHALL be resolved once per load and used for **every** artefact the
adapter reads — the weights and the processor alike. An adapter that resolves
them separately can pair weights from one snapshot with preprocessing from
another, which no width check and no tensor check can see.

A revision is a commit of a particular repository. So the service SHALL refuse
to start when a checkpoint name is configured away from its default while its
revision is left at the default, because that default names a commit of the
repository that was replaced.

#### Scenario: A model is loaded at its default revision
- **WHEN** a build enables a storage model and configures no revision for it
- **THEN** the adapter loads every artefact of that checkpoint at the revision
  this repository verified, and the same load a year later reads the same
  weights

#### Scenario: A substituted checkpoint without a revision
- **WHEN** a checkpoint name is configured away from its default and its
  revision is left at the default
- **THEN** the service refuses to start and names the setting, because the
  default revision is a commit of a repository that is no longer the one
  configured

#### Scenario: The weights and the preprocessing come from one snapshot
- **WHEN** an adapter reads a checkpoint's weights and its processor
- **THEN** both are read at the one revision resolved for that load, so they
  cannot come from different snapshots
