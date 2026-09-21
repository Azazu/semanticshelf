## Purpose

Importing a directory of pictures in one command: which files are considered,
where the walk may not go, what is stored about a file's origin, what a dry run
promises to leave untouched, and what the summary of a run reports.

## ADDED Requirements

### Requirement: A folder is imported through the pipeline an upload uses

Importing a folder SHALL store each accepted picture exactly as an upload of
the same bytes would: the format detected from the bytes, the same caps and
refusals, the same thumbnail, the same generated storage name, the same
duplicate rule on the content hash, and the same work queued for every enabled
model in the same transaction as the asset. An import SHALL NOT accept a
picture an upload would refuse, and SHALL NOT refuse one an upload would
accept.

The source of an imported asset SHALL be recorded as a folder import, so the
store can tell the two entrances apart.

#### Scenario: A picture an upload would accept
- **WHEN** a folder holding a valid picture is imported
- **THEN** the asset is stored with its files, its row and its work, and it is
  indistinguishable from the same picture uploaded, except that its source says
  it came from a folder

#### Scenario: A picture an upload would refuse
- **WHEN** a folder holds a file that decodes as a picture but breaks one of
  the rules an upload enforces
- **THEN** it is refused with the same reason an upload gives, nothing is
  stored for it, and the run continues with the rest of the folder

#### Scenario: A file already in the store
- **WHEN** a folder holds a picture whose bytes are already stored
- **THEN** no second asset is created, the existing asset is left exactly as it
  was, and the file is counted as already stored

### Requirement: The walk stays inside the folder it was given

The import SHALL read only regular files inside the directory it was named,
and SHALL NOT be led out of it. A symbolic link to a directory SHALL NOT be
descended into. A symbolic link whose target is outside the imported directory
SHALL NOT be read. Anything that is not a regular file — a device node, a
socket, a fifo — SHALL NOT be opened. Each of these SHALL be reported as
skipped with its reason rather than passed over in silence.

Without the recursive option the import SHALL consider only the files directly
in the named directory; with it, the files of every directory beneath it.

#### Scenario: A link that leaves the tree
- **WHEN** the imported directory holds a symbolic link to a file outside it
- **THEN** that file is not read and not stored, and the run reports it as
  skipped

#### Scenario: A link that would make the walk endless
- **WHEN** the imported directory holds a symbolic link to one of its own
  parents
- **THEN** the walk terminates, having visited each real file at most once

#### Scenario: Something that is not a file
- **WHEN** the imported directory holds a fifo, a socket or a device node
- **THEN** it is not opened, and the run reports it as skipped

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
and SHALL NOT silently replace what the import records about the file's origin.

#### Scenario: A picture in a subdirectory
- **WHEN** a picture nested in subdirectories is imported
- **THEN** its original filename is the file's own name, and its metadata
  carries the path relative to the imported directory

#### Scenario: Tags and metadata for the whole run
- **WHEN** a folder is imported with tags and metadata
- **THEN** every asset created by that run carries them, normalised as an
  upload would normalise them, alongside the recorded origin

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
run at all — the directory does not exist, is not a directory, or cannot be
read.

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

### Requirement: An import ends with vectors, not with a backlog

After a successful import the work it queued SHALL be carried out before the
command returns, through the same execution an uploaded picture's work goes
through, unless the run was asked to leave the work queued. The command SHALL
report how much work it carried out, and work that fails SHALL NOT fail the
import: it stays in the queue under the rules the queue already has.

#### Scenario: A folder is imported
- **WHEN** a folder of pictures is imported without asking for the work to be
  left queued
- **THEN** the command returns only after the imported assets have their
  vectors, and says how much work it did

#### Scenario: The work is left for later
- **WHEN** a folder is imported with the work left queued
- **THEN** the assets exist with their work waiting, no vector is computed, and
  the command says so
