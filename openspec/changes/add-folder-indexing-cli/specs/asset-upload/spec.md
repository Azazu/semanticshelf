## MODIFIED Requirements

### Requirement: A picture is accepted on its bytes, not on its labels

The service SHALL determine a file's format by decoding its content, never
from the filename, from a file extension, or from the content type a client
declared. Only JPEG, PNG and WebP SHALL be accepted. A declared type that
disagrees with the detected one SHALL NOT be an error: the detected format
wins and is what the service records and later serves. Anything that does not
decode as one of the three SHALL be refused — with 415 problem details when it
arrived over HTTP, and with the same reason in the summary when it came from a
folder import — and nothing SHALL be stored for it.

This rule holds at every entrance to the store. A folder import MAY use a
file's extension to decide which files are worth reading, but SHALL NOT use it
to decide what a file is: a file with a picture's extension that does not
decode is refused exactly as an upload of the same bytes would be.

#### Scenario: A picture whose declared type is wrong
- **WHEN** a PNG is uploaded with a filename ending in `.jpg` and a part
  header claiming `image/jpeg`
- **THEN** it is accepted, and the asset records PNG as its content type

#### Scenario: A file that is not a picture
- **WHEN** a file that decodes as no accepted format is uploaded
- **THEN** the answer is 415 problem details, nothing is written to disk and
  no asset row exists

#### Scenario: A picture of a format the service does not accept
- **WHEN** a picture in a format the decoder recognises but the service does
  not accept is uploaded
- **THEN** the answer is 415 problem details naming that detected format

#### Scenario: A file whose extension lies, in a folder import
- **WHEN** a folder holding a text file named with a picture's extension is
  imported
- **THEN** it is refused for the same reason an upload of those bytes would be,
  and nothing is stored for it

### Requirement: Identical bytes are one asset

The content hash of a stored file SHALL be unique among assets. A file whose
bytes are already stored SHALL NOT create a second asset and SHALL write
nothing — no file, no row: over HTTP it is refused with 409 problem details
carrying the identifier of the existing asset, and in a folder import it is
counted as already stored and the run continues. Two identical arrivals racing
each other SHALL produce exactly one asset, whichever order they arrive in.

#### Scenario: The same file uploaded twice
- **WHEN** a file whose bytes are already stored is uploaded again
- **THEN** the answer is 409 problem details naming the existing asset, and
  the store still holds exactly one asset for those bytes

#### Scenario: Two identical uploads at the same time
- **WHEN** two uploads of identical bytes are processed concurrently
- **THEN** one succeeds with 201 and the other is refused with 409, and
  neither leaves a file the surviving asset does not own

#### Scenario: The same picture twice in one folder
- **WHEN** a folder holding the same bytes under two names is imported
- **THEN** exactly one asset exists for those bytes and the second file is
  counted as already stored

### Requirement: Tags and metadata are normalised the same way everywhere

A tag SHALL be normalised (trimmed, lower-cased, Unicode-normalised) and then
match the tag pattern; duplicates SHALL collapse; the number of distinct tags
per asset SHALL be bounded. Metadata SHALL be a JSON object within bounded
size and nesting depth. A value that does not satisfy these rules SHALL be
refused naming the offending value — with 422 problem details over HTTP, and
before a folder import reads any file. The same normalisation SHALL be applied
wherever tags or metadata enter the system, so that a tag written at upload,
a tag given for an import and the same tag written by a later edit are one
tag.

Metadata the service records about a stored file's origin SHALL follow the
same bounds as any other metadata, and SHALL NOT be overwritten by metadata
given for a run.

#### Scenario: Tags that differ only in case or spacing
- **WHEN** an upload carries the same tag several times in different case or
  with surrounding spaces
- **THEN** the asset ends up with that tag once, in its normalised form

#### Scenario: A tag outside the pattern
- **WHEN** an upload carries a tag that does not match the pattern after
  normalisation
- **THEN** the answer is 422 problem details naming that value, and nothing is
  stored

#### Scenario: Metadata that is not an object, too large or too deep
- **WHEN** metadata is uploaded that is not a JSON object, or exceeds the size
  or nesting bound
- **THEN** the answer is 422 problem details and nothing is stored

#### Scenario: A tag an import cannot use
- **WHEN** a folder import is given a tag that does not match the pattern
- **THEN** the run is refused naming that value before any file is read, and
  nothing is stored
