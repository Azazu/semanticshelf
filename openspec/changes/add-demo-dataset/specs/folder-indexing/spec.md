## MODIFIED Requirements

### Requirement: What is stored says where the picture came from

An imported asset SHALL carry the file's own name as the original filename it
arrived with, and SHALL carry the file's path relative to the imported
directory as metadata. The relative path SHALL NOT be used to build any path
the service reads or writes, and the original filename SHALL remain a single
name with no directory in it, exactly as an upload's is.

Tags and metadata given for the run SHALL be applied to every asset it
creates, through the same normalisation and the same limits an upload applies,
and SHALL NOT replace what the import records about the file's origin.

A picture MAY be accompanied by a sidecar file, named after it and lying beside
it, carrying tags and metadata for that picture alone. When one is present its
tags SHALL be added to the run's tags and its metadata merged over the run's
metadata, through the same normalisation and the same limits, and neither SHALL
replace what the import records about the file's origin. A sidecar SHALL NOT be
considered a picture to import. A sidecar that cannot be read, is not an
object, exceeds the limits, or carries a tag the service would refuse SHALL
cause its own picture to be refused with a reason naming the sidecar, and the
run SHALL continue with the rest of the folder.

#### Scenario: A picture in a subdirectory
- **WHEN** a picture nested in subdirectories is imported
- **THEN** its original filename is the file's own name, and its metadata
  carries the path relative to the imported directory

#### Scenario: Tags and metadata for the whole run
- **WHEN** a folder is imported with tags and metadata
- **THEN** every asset created by that run carries them, normalised as an
  upload would normalise them, alongside the recorded origin

#### Scenario: A run that tries to set the origin itself
- **WHEN** a folder is imported with metadata that names the key the import
  records the origin under
- **THEN** the stored origin is the one the import recorded, not the one the
  run supplied

#### Scenario: Tags that are not acceptable
- **WHEN** a folder is imported with a tag the service would refuse at upload
- **THEN** the run refuses before reading any file, and nothing is stored

#### Scenario: A picture with a sidecar
- **WHEN** a folder holding a picture with its sidecar is imported
- **THEN** that asset carries the sidecar's tags together with the run's, and
  the sidecar's metadata over the run's, with the recorded origin intact

#### Scenario: A sidecar that tries to set the origin
- **WHEN** a sidecar names the key the import records the origin under
- **THEN** the stored origin is the one the import recorded, not the one the
  sidecar supplied

#### Scenario: A sidecar the service cannot accept
- **WHEN** a sidecar cannot be read, is not an object, exceeds the limits, or
  carries a tag the service would refuse
- **THEN** its picture is refused with a reason naming the sidecar, nothing is
  stored for that picture, and the run continues with the rest of the folder

#### Scenario: A sidecar is not a picture
- **WHEN** a folder holding pictures and their sidecars is imported
- **THEN** the sidecars are not reported as files the run refused or skipped,
  and no asset is created for one
