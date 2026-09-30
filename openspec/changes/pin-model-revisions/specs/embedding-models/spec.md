## ADDED Requirements

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
