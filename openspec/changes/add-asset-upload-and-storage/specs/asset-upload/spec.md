## Purpose

What happens when a picture arrives from outside the service: what is
accepted, what is refused and with which answer, what ends up on disk and in
the store, and what states a crash can leave behind.

## ADDED Requirements

### Requirement: A picture is accepted on its bytes, not on its labels

The service SHALL determine an uploaded file's format by decoding its content,
never from the filename or from the content type the client declared. Only
JPEG, PNG and WebP SHALL be accepted. A declared type that disagrees with the
detected one SHALL NOT be an error: the detected format wins and is what the
service records and later serves. Anything that does not decode as one of the
three SHALL be refused with 415 problem details, naming the detected format
when the decoder recognised it.

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

### Requirement: Every limit is enforced before the work it bounds

The service SHALL refuse an upload larger than the configured byte limit while
the request is being read, before its content is decoded, with 413. The bound
SHALL apply to the whole request body — every part and the multipart framing
around them — and not only to the file part, and it SHALL hold for a request
that declares no length or declares a false one. It SHALL refuse
a picture whose decoded pixel count exceeds the configured cap with 422, and
the cap SHALL be applied before the pixels are allocated, so that a small file
claiming enormous dimensions is refused rather than decoded. It SHALL refuse a
picture whose shorter side is below the configured minimum with 422. A refusal
SHALL leave nothing on disk and no row in the store.

#### Scenario: A file over the byte limit
- **WHEN** an upload whose file part exceeds the configured byte limit arrives
- **THEN** the answer is 413 problem details, and the service never decoded
  the content

#### Scenario: A request with an unreasonable number of parts
- **WHEN** a request arrives with far more parts than an upload can have
- **THEN** it is refused as problem details before those parts are processed

#### Scenario: A body over the limit in several parts
- **WHEN** a request whose parts are each under the limit but whose whole body
  exceeds it arrives
- **THEN** the answer is 413 problem details

#### Scenario: A request that does not declare its length
- **WHEN** an oversized body arrives without a declared length, or with one
  that understates it
- **THEN** it is still refused with 413, because the bound counts the bytes
  that arrive rather than the number the client claims

#### Scenario: A decompression bomb
- **WHEN** a small file declaring dimensions beyond the pixel cap is uploaded
- **THEN** the answer is 422 problem details, and the pixels were never
  allocated

#### Scenario: The pixel cap is enforced at the number it names
- **WHEN** a picture of exactly the configured pixel cap is uploaded, and
  another of the cap plus one pixel
- **THEN** the first is accepted and the second is refused with 422

#### Scenario: A picture smaller than the minimum side
- **WHEN** a picture whose shorter side is under the configured minimum is
  uploaded
- **THEN** the answer is 422 problem details and nothing is stored

### Requirement: Identical bytes are one asset

The content hash of an uploaded file SHALL be unique among assets. An upload
whose bytes are already stored SHALL be refused with 409 problem details
carrying the identifier of the existing asset, and SHALL write nothing — no
file, no row. Two identical uploads racing each other SHALL produce exactly
one asset and one 409, whichever order they arrive in.

#### Scenario: The same file uploaded twice
- **WHEN** a file whose bytes are already stored is uploaded again
- **THEN** the answer is 409 problem details naming the existing asset, and
  the store still holds exactly one asset for those bytes

#### Scenario: Two identical uploads at the same time
- **WHEN** two uploads of identical bytes are processed concurrently
- **THEN** one succeeds with 201 and the other is refused with 409, and
  neither leaves a file the surviving asset does not own

### Requirement: An asset exists whole or not at all

An asset SHALL consist of its original bytes, a thumbnail and a row, and the
service SHALL create them in an order that never leaves a row pointing at a
file that is not there: both files SHALL be in place before the row is
written, and a failure to write the row SHALL remove them. A thumbnail that
cannot be produced SHALL fail the upload. A crash between the files and the
row MAY leave files with no row — the only residue the design permits, and one
the prune command below finds.

#### Scenario: The row cannot be written
- **WHEN** the row fails to insert after both files are in place
- **THEN** the upload is refused and neither file remains

#### Scenario: The thumbnail cannot be produced
- **WHEN** a picture decodes but its thumbnail cannot be written
- **THEN** the upload is refused, no row exists, and no file of that upload
  remains

#### Scenario: A file is never half-written
- **WHEN** an upload is interrupted while writing either file
- **THEN** no partially written file is visible under the name the service
  serves, because each file becomes visible only under its final name

### Requirement: Stored paths are derived, never supplied

Every filesystem path the service touches SHALL be derived from the identifier
the service generated for the asset and the format it detected. No part of any
path SHALL come from a client — not the filename, not a header, not a
parameter. The original filename MAY be kept as metadata only, trimmed to a
bounded length and stripped of control characters and path separators. Nothing
under the media root SHALL be reachable by path from outside the service.

#### Scenario: A filename that tries to escape
- **WHEN** a file is uploaded with a filename containing path separators or
  parent-directory segments
- **THEN** the stored file's path is derived from the asset's identifier
  alone, the file lands under the media root, and the recorded filename
  contains no separator

#### Scenario: A request for a path
- **WHEN** a client asks for a path under the media root rather than for an
  asset identifier
- **THEN** no endpoint serves it

#### Scenario: A filename carrying control characters or beyond the bound
- **WHEN** a file arrives with a name holding control characters, or longer
  than the stored bound
- **THEN** the recorded name holds no control character and is within the
  bound, and the asset is otherwise stored normally

#### Scenario: A filename with nothing usable left
- **WHEN** a file arrives with a name that is empty after normalisation
- **THEN** the asset records no original filename rather than an empty one

### Requirement: The thumbnail carries nothing over from the original

The thumbnail SHALL be re-encoded from the decoded pixels rather than derived
from the original file, so that no metadata block of the original — camera
data, colour profile, comment, or anything hidden in one — is carried into it.
Its longest side SHALL be at most the configured thumbnail size, preserving
aspect ratio, and it SHALL be stored beside the original. A picture already
smaller than that size SHALL keep its own, because enlarging it would spend
bytes inventing detail the original does not have.

#### Scenario: A picture with metadata
- **WHEN** a picture carrying metadata blocks is uploaded
- **THEN** the stored original keeps them byte for byte, and the thumbnail
  contains none of them

#### Scenario: Thumbnail proportions
- **WHEN** a picture wider than it is tall and larger than the thumbnail size
  is uploaded
- **THEN** the thumbnail's longest side is the configured size and its aspect
  ratio matches the original within rounding

#### Scenario: A picture smaller than the thumbnail size
- **WHEN** a picture whose longest side is already under the thumbnail size is
  uploaded
- **THEN** its thumbnail keeps the original's dimensions rather than being
  enlarged, and is still a thumbnail in the stored format

### Requirement: The upload request has one shape

An upload SHALL carry exactly one file part; a request with none and a request
with several SHALL both be refused with 422 naming the problem. Tags MAY
arrive as repeated fields or as one comma-separated field, and both forms
SHALL produce the same normalised set. Metadata SHALL arrive as a string
holding a JSON object, whose length is checked before it is parsed, so an
oversized value is refused without being built.

#### Scenario: No file part
- **WHEN** an upload carries no file part
- **THEN** the answer is 422 problem details naming the missing part

#### Scenario: Several file parts
- **WHEN** an upload carries more than one file part
- **THEN** the answer is 422 problem details and nothing is stored

#### Scenario: Tags in either form
- **WHEN** the same tags arrive once as repeated fields and once as one
  comma-separated field
- **THEN** both uploads produce the same set of tags on their assets

#### Scenario: Metadata that is not a JSON object
- **WHEN** metadata arrives as a string that is not a JSON object
- **THEN** the answer is 422 problem details naming the field

### Requirement: Tags and metadata are normalised the same way everywhere

A tag SHALL be normalised (trimmed, lower-cased, Unicode-normalised) and then
match the tag pattern; duplicates SHALL collapse; the number of distinct tags
per asset SHALL be bounded. Metadata SHALL be a JSON object within bounded
size and nesting depth. A value that does not satisfy these rules SHALL be
refused with 422 naming the offending value. The same normalisation SHALL be
applied wherever tags or metadata enter the system, so that a tag written at
upload and the same tag written by a later edit are one tag.

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

### Requirement: Orphan files are findable and removable

The service SHALL offer a maintenance command that reports files under the
media root with no asset row and asset rows whose files are missing. It SHALL
change nothing unless explicitly asked to act; when asked, it SHALL remove the
orphan files and mark the indexing work of an asset whose files are gone as
failed, with a reason naming the missing file.

A file an upload has placed under the media root but not yet recorded is
indistinguishable from an orphan, and an upload may be delayed without bound,
so the protection SHALL NOT depend on how long one takes. Two rules provide it
together.

An upload SHALL NOT place anything under the media root before it is certain
to keep it: what it receives from the client, and whatever it must read to
decide, SHALL live outside the root. The command therefore cannot see an
upload that is still arriving, and MAY run freely beside one. The service
SHALL verify that this holds in its own configuration rather than assume it: a
deployment whose temporary location lies inside the media root SHALL be
reported by the readiness probe and SHALL refuse the upload, rather than
silently reintroducing the race.

From the moment an upload does place a file under the root until its row is
stored, it SHALL hold a shared claim; the command SHALL take that claim
exclusively before it changes anything, and SHALL report and change nothing
when it cannot.

In addition, the command SHALL ignore files younger than a configured grace
period and report how many it ignored, as a margin for a run pointed at a
store the uploading service does not use.

#### Scenario: Files left by a crash
- **WHEN** the command runs with files under the media root that no asset row
  refers to
- **THEN** it reports them, and it removes them only when asked to act

#### Scenario: A row whose file is gone
- **WHEN** the command runs with an asset row whose file is missing
- **THEN** it reports that asset, and when asked to act it marks that asset's
  indexing work failed with a reason naming the missing file

#### Scenario: A dry run changes nothing
- **WHEN** the command runs without being asked to act
- **THEN** no file is removed and no row is changed

#### Scenario: An upload that has placed its files but not its row
- **WHEN** the command runs and is asked to act while an upload holds the
  claim, however long that upload takes
- **THEN** the command changes nothing and says an upload is in flight, and
  the upload completes with both its files in place

#### Scenario: An upload that is still arriving
- **WHEN** the command runs and is asked to act while an upload is still being
  received and inspected, however long that takes
- **THEN** the command may proceed, finds nothing belonging to that upload
  under the media root, and the upload completes with both its files in place

#### Scenario: A deployment whose temporary location is inside the media root
- **WHEN** the service is configured so that what it receives would land
  inside the media root
- **THEN** readiness reports it and an upload is refused, because the
  protection above no longer holds

#### Scenario: No upload in flight
- **WHEN** the command runs with no upload in flight
- **THEN** it proceeds, and files older than the grace period with no asset
  row are reported and, when it is asked to act, removed
