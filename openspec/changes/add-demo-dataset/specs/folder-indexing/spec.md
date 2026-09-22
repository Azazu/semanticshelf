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

### Requirement: Only a regular file inside the folder is ever read

The import SHALL read a file only through a descriptor it opened itself, and
SHALL decide what that file is from that descriptor rather than from its path:
a name that was safe when it was listed SHALL NOT be able to become something
else before it is read. This SHALL hold for every file the import reads,
whether it is a candidate picture or the sidecar of one, and in every directory
the run walks.

A symbolic link SHALL NOT be read, wherever it points. A directory reached
through a symbolic link SHALL NOT be walked. Anything that is not a regular
file — a device node, a socket, a fifo — SHALL NOT be read, and opening it
SHALL NOT be able to block the run. Each of these SHALL be reported as skipped
with its reason rather than passed over in silence; when it is a sidecar, its
own picture SHALL be refused with that reason rather than imported without it,
because a picture whose provenance could not be read is not the picture the run
was asked to import.

The directory named for the run SHALL be opened once before the walk starts,
and every step of the run — counting, walking, importing — SHALL work in the
directory that was opened then, not in whatever the name refers to later. The
directory the run reports SHALL be the directory it read: a run SHALL NOT be
able to read one directory while naming another. A run named with a symbolic
link to a directory therefore behaves as if it had been named with that
directory, and replacing that name, or any part of it, once the run has begun
SHALL NOT be able to send the run into another tree.
Without the recursive option the import SHALL consider only the files directly
in that directory; with it, the files of every directory beneath it.

#### Scenario: An entry replaced between being listed and being read
- **WHEN** a file the walk has listed as a candidate is replaced, before it is
  read, by a symbolic link pointing outside the folder or by a fifo
- **THEN** nothing outside the folder is read, the run does not block, and the
  entry is reported as skipped

#### Scenario: A sidecar that is a symbolic link
- **WHEN** a picture's sidecar is a symbolic link, wherever it points
- **THEN** it is not read, nothing outside the folder is opened, and the
  picture is refused with that reason

#### Scenario: A sidecar replaced between being found and being read
- **WHEN** a sidecar is replaced, after the picture beside it was listed and
  before the sidecar is read, by a symbolic link or by a file that is not
  regular
- **THEN** it is not read, the run does not block, and the picture is refused
  with that reason

#### Scenario: A link that leaves the tree
- **WHEN** the imported directory holds a symbolic link to a file outside it
- **THEN** that file is not read and not stored, and the run reports it as
  skipped

#### Scenario: A link that would make the walk endless
- **WHEN** the imported directory holds a symbolic link to one of its own
  parents
- **THEN** the walk terminates, having read each real file at most once

#### Scenario: Something that is not a file
- **WHEN** the imported directory holds a fifo, a socket or a device node
- **THEN** none of them is read, the run does not block on any of them, and
  each is reported as skipped

#### Scenario: The folder itself is a link
- **WHEN** a run names a symbolic link that points at a directory of pictures
- **THEN** the pictures are imported as if the directory had been named
  directly

#### Scenario: The folder's name is taken over after the run begins
- **WHEN** the name a run was given is replaced, after the run has begun, by a
  link to a different directory
- **THEN** the run reads the directory it began in, reports that directory, and
  reads nothing from the other one

#### Scenario: The folder's name is taken over as the run begins
- **WHEN** the name is replaced at the moment the run opens it
- **THEN** whichever directory the run ends up holding is the one it reads and
  the one it reports — the two are never different directories

#### Scenario: A folder inside the folder
- **WHEN** a directory holding pictures in subdirectories is imported without
  the recursive option, and again with it
- **THEN** the first run considers only the top level and the second considers
  every level
