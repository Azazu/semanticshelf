## Purpose

Importing a directory of pictures in one command: which files are considered,
what the walk may not read, what is stored about a file's origin, what a dry
run promises to leave untouched, what the summary of a run reports, and what
the command guarantees about the work it queued.

## ADDED Requirements

### Requirement: A folder is imported through the pipeline an upload uses

Importing a folder SHALL store each accepted picture exactly as an upload of
the same bytes would: the format detected from the bytes, the same caps and
refusals, the same thumbnail, the same generated storage name, the same
duplicate rule on the content hash, and the same work queued for every enabled
model in the same transaction as the asset. An import SHALL NOT accept a
picture an upload would refuse, and SHALL NOT refuse one an upload would
accept.

An imported asset SHALL differ from the same picture uploaded in exactly two
ways: its source SHALL say it came from a folder, and its metadata SHALL carry
the recorded origin described below. Everything else about it — its content
type, its dimensions, its size, its content hash, the files on disk and the
work queued for it — SHALL be the same.

#### Scenario: A picture an upload would accept
- **WHEN** a folder holding a valid picture is imported
- **THEN** the asset is stored with its files, its row and its work, and it
  matches the same picture uploaded in every stored value except its source and
  its recorded origin

#### Scenario: A picture an upload would refuse
- **WHEN** a folder holds a file that decodes as a picture but breaks one of
  the rules an upload enforces
- **THEN** it is refused with the same reason an upload gives, nothing is
  stored for it, and the run continues with the rest of the folder

#### Scenario: A file already in the store
- **WHEN** a folder holds a picture whose bytes are already stored
- **THEN** no second asset is created, the existing asset is left exactly as it
  was, and the file is counted as already stored

#### Scenario: A file with no bytes at all
- **WHEN** a folder holds a zero-byte file named like a picture
- **THEN** it is refused as undecodable, exactly as an upload of no bytes is,
  and nothing is stored for it

#### Scenario: A folder with nothing to import
- **WHEN** an empty directory is imported, and again a directory holding no
  file the service would consider
- **THEN** both runs succeed, store nothing, and report counts of zero with the
  reason each file was skipped

### Requirement: Only a regular file inside the folder is ever read

The import SHALL read a file only through a descriptor it opened itself, and
SHALL decide what that file is from that descriptor rather than from its path:
a name that was safe when it was listed SHALL NOT be able to become something
else before it is read.

A symbolic link SHALL NOT be read, wherever it points. A directory reached
through a symbolic link SHALL NOT be walked. Anything that is not a regular
file — a device node, a socket, a fifo — SHALL NOT be read, and opening it
SHALL NOT be able to block the run. Each of these SHALL be reported as skipped
with its reason rather than passed over in silence.

The directory named for the run SHALL be resolved once before the walk starts,
and the walk SHALL proceed from the resolved directory; a run named with a
symbolic link to a directory therefore behaves as if it had been named with
that directory. Without the recursive option the import SHALL consider only the
files directly in that directory; with it, the files of every directory beneath
it.

#### Scenario: An entry replaced between being listed and being read
- **WHEN** a file the walk has listed as a candidate is replaced, before it is
  read, by a symbolic link pointing outside the folder or by a fifo
- **THEN** nothing outside the folder is read, the run does not block, and the
  entry is reported as skipped

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

#### Scenario: A folder inside the folder
- **WHEN** a directory holding pictures in subdirectories is imported without
  the recursive option, and again with it
- **THEN** the first run considers only the top level and the second considers
  every level

### Requirement: What is stored says where the picture came from

An imported asset SHALL carry the file's own name as the original filename it
arrived with, and SHALL carry the file's path relative to the imported
directory as metadata. The relative path SHALL NOT be used to build any path
the service reads or writes, and the original filename SHALL remain a single
name with no directory in it, exactly as an upload's is.

Tags and metadata given for the run SHALL be applied to every asset it
creates, through the same normalisation and the same limits an upload applies,
and SHALL NOT replace what the import records about the file's origin.

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

### Requirement: A dry run changes nothing

A dry run SHALL report what a real run would do without writing anything: no
file under the media root, no asset, no work, no change to any existing asset.
It SHALL still read and inspect the files, so that the refusals it reports are
the refusals a real run would give, and it SHALL still say which files are
already stored.

#### Scenario: A dry run over a folder with new, refused and stored pictures
- **WHEN** such a folder is imported with the dry-run option
- **THEN** the summary names what would be created, what would be refused and
  what is already stored, and afterwards the store and the media root are
  byte-for-byte what they were before

### Requirement: A run says what happened to every file it considered

An import SHALL end with a summary that accounts for every file it considered:
how many assets were created, how many files were already stored, how many
were refused and for what reason, and how many were skipped and why. The
summary SHALL be the same whether the run was a dry run or not, apart from
saying which it was.

An import SHALL NOT stop at the first file it cannot use: a refusal is
recorded and the run continues. It SHALL fail as a whole only when it cannot
run at all — the named directory does not exist, is not a directory once
resolved, or cannot be read.

#### Scenario: A folder with a mix of files
- **WHEN** a folder holding valid pictures, an unreadable file, a file already
  stored and a file that is not a picture is imported
- **THEN** every one of them appears in the counts, the valid pictures are
  stored, and the command reports success

#### Scenario: A directory that is not there
- **WHEN** an import names a directory that does not exist or is not a
  directory
- **THEN** the command refuses with a message naming it, stores nothing, and
  exits with a non-zero status

### Requirement: An import finishes the work it created, or says what it left

Unless the run was asked to leave the work queued, the import SHALL carry out
the work it created for the assets it created, and SHALL NOT be satisfied by
carrying out unrelated work that happened to be waiting: when it returns, every
asset it created SHALL either have its vectors or have work the queue still
owns, and the summary SHALL say how many of each — indexed, still queued, or
failed with the reason the queue recorded.

Work that fails SHALL NOT fail the import. The import SHALL NOT wait
indefinitely for work it cannot claim: when a pass claims nothing while work
of its own assets is still unfinished, the run SHALL end and report that work
as still queued.

#### Scenario: A folder is imported
- **WHEN** a folder of pictures is imported without asking for the work to be
  left queued
- **THEN** the command returns only after every asset it created has its
  vectors, and says how many it indexed

#### Scenario: A queue that already holds other work
- **WHEN** a folder is imported while the queue already holds more due work for
  other assets than one batch can take
- **THEN** the imported assets still end with their vectors, and the run does
  not report success while its own work is unfinished

#### Scenario: Work that cannot be done
- **WHEN** a picture is imported whose work fails every attempt the queue
  allows
- **THEN** the import still succeeds, the asset exists, and the summary reports
  that work as failed with its reason

#### Scenario: The work is left for later
- **WHEN** a folder is imported with the work left queued
- **THEN** the assets exist with their work waiting, no vector is computed, and
  the command says so
