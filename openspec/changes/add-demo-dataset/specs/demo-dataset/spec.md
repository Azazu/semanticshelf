## Purpose

The corpus the service can be demonstrated on: where its pictures come from,
which of them may be taken, what is recorded about each one, what bounds the
fetching, what a half-finished run leaves behind, and what running the commands
again is promised to do.

## ADDED Requirements

### Requirement: The demo corpus comes from one named, recorded source

The service SHALL fetch its demo corpus from a single public dataset, named in
the repository's documentation together with the licence of its pictures and of
its annotations. The dataset SHALL NOT be chosen at runtime, and no command
SHALL fetch anything from a host the documentation does not name.

The commands that fetch it SHALL be operator commands only. Neither the API nor
the background worker SHALL make any request to that source.

#### Scenario: The source is documented
- **WHEN** the repository is read
- **THEN** it names the dataset, the licences its pictures may carry, the
  licences the command accepts, and how attribution is given

#### Scenario: The service itself never fetches
- **WHEN** the application that serves requests is built
- **THEN** nothing it loads reaches the demo corpus module, and no request to
  the dataset's host can originate from serving a request

### Requirement: Only a picture whose licence permits it is taken

Every picture SHALL carry, in the dataset's own manifest, a licence that the
command recognises as permitting reuse. The command SHALL hold an explicit list
of accepted licences, SHALL decide each picture against the manifest rather
than against an assumption about the dataset as a whole, and SHALL NOT download
a picture whose licence is absent from the manifest, unrecognised, or outside
that list.

The run SHALL report how many pictures it refused for their licence, and the
licence notice SHALL be printed whether or not anything was downloaded.

#### Scenario: A picture under an accepted licence
- **WHEN** the manifest gives a picture a licence on the accepted list
- **THEN** it is a candidate for download

#### Scenario: A picture under a licence that is not accepted
- **WHEN** the manifest gives a picture a licence that permits no reuse, or a
  licence the command does not recognise, or no licence at all
- **THEN** it is not downloaded, it is counted as refused for its licence, and
  the run continues

#### Scenario: The notice is always shown
- **WHEN** the download command finishes, including a run that downloaded
  nothing
- **THEN** it prints the dataset's licence notice and where the details are
  recorded

### Requirement: Each picture is written with its tags and its provenance

For every picture it keeps, the command SHALL write the picture's bytes and,
beside them, the tags the dataset's own labelling gives it and the provenance
of that picture: the dataset it came from, the identifier it carries there, its
licence, the address it can be seen at, and its author where the dataset
records one. A field the dataset does not supply SHALL be absent rather than
invented.

A dataset's label is not a tag. The command SHALL convert a label into a
candidate tag by a rule this capability states — runs of whitespace become the
separator a tag may contain — and SHALL then require that candidate to survive
the service's own tag normalisation unchanged in meaning. A label that does not
survive it SHALL be dropped rather than making the picture unusable, and the
number of tags SHALL NOT exceed what an asset may carry.

#### Scenario: A picture with labels
- **WHEN** a picture the dataset labels is written
- **THEN** its tags are those labels converted and normalised, and its
  provenance names the dataset, the identifier, the licence and the address

#### Scenario: A label of several words
- **WHEN** a label consists of words separated by whitespace
- **THEN** it becomes one tag whose words are joined by the separator a tag may
  contain

#### Scenario: A field the dataset does not have
- **WHEN** the dataset records no author for a picture
- **THEN** the provenance carries no author key, and the documentation says
  attribution is by address

#### Scenario: A label that cannot become a tag
- **WHEN** a label cannot be converted into a tag the service would accept
- **THEN** that label is dropped, the rest are kept, and the picture is still
  written

### Requirement: Every transfer is bounded, and each kind of object by its own bound

Every request the commands make SHALL carry a timeout and SHALL be refused
rather than followed when it is answered with a redirect to another host.

Each kind of object SHALL be bounded by what that kind may weigh, and the
bounds SHALL be separate because the objects are: a picture SHALL be abandoned
when its response passes the size the service accepts for a picture, and the
manifest archive SHALL be abandoned when its response passes the archive bound
this capability declares, which SHALL be documented and SHALL be far larger
than a picture's. A transfer abandoned for any of these reasons SHALL leave
nothing behind for the object it was fetching.

The archive SHALL be read for the one member the command needs, by exact name,
and SHALL be refused when that member is absent or when its declared
uncompressed size exceeds the member bound. Nothing else SHALL be extracted
from the archive.

A response that is not the object it was supposed to be SHALL be discarded
rather than written: a picture's bytes SHALL be accepted only if they decode as
a picture the service would accept.

#### Scenario: The count is honoured
- **WHEN** a download of a given number of pictures is requested
- **THEN** no more than that many pictures are written, and the run says how
  many it wrote

#### Scenario: A picture's response grows past the picture bound
- **WHEN** a picture's response exceeds the size a picture may have
- **THEN** the download of that picture is abandoned, nothing is left behind
  for it, and the run continues with the next one

#### Scenario: The archive's response grows past the archive bound
- **WHEN** the manifest archive's response exceeds the archive bound
- **THEN** the transfer is abandoned, nothing of it is left in the target
  directory, the command fails naming the bound, and no picture is downloaded

#### Scenario: A transfer that does not answer in time
- **WHEN** a request for the archive or for a picture does not answer within
  the timeout
- **THEN** it is abandoned, nothing is left behind for that object, and the
  archive case fails the command while the picture case is counted and the run
  continues

#### Scenario: A redirect away from the named host
- **WHEN** a request is answered with a redirect to another host
- **THEN** it is not followed; for a picture that picture is counted as refused
  and the run continues, and for the archive the command fails

#### Scenario: An archive without the member it must hold
- **WHEN** the manifest archive does not contain the member the command needs,
  or that member declares an uncompressed size above the member bound
- **THEN** the command fails with a message naming what it expected, and no
  picture is downloaded

#### Scenario: Bytes that are not a picture
- **WHEN** a response arrives that does not decode as a picture the service
  accepts
- **THEN** it is discarded, counted as refused, and nothing is written for it

### Requirement: Nothing the dataset says becomes a path or a command

Every file the command writes SHALL be named from values the command itself
controls: an identifier it validated and an extension it derived from the bytes
it decoded. No name, path or address from the manifest SHALL be used to build a
filesystem path, and no downloaded file SHALL be written outside the directory
the operator named.

#### Scenario: A manifest entry that names a path
- **WHEN** the manifest gives a picture a name containing directory
  separators, parent references, or an absolute path
- **THEN** no file is written outside the target directory, and the picture is
  stored under a name the command derived itself

### Requirement: A file appears whole, or does not appear

Every file the commands write — the archive, a picture, a picture's sidecar —
SHALL be written under a name unique to the run that is writing it and SHALL be
moved into its final name only once it is complete. A run that dies SHALL NOT
be able to leave a file under a final name that a later run would treat as
finished.

What a dead run may leave SHALL be exactly two things, and both SHALL be
recoverable without operator action: a staging file, which no later run reads
because every run stages under its own name; and a sidecar whose picture never
arrived, which nothing imports because only a picture is a candidate for
import, and which the next run for that picture overwrites.

Two runs writing into one directory SHALL NOT be able to produce a file that is
part of one run and part of another: each stages under its own name, and the
final name receives one complete file or another, never a mixture.

#### Scenario: A run that dies while fetching
- **WHEN** a download is killed while a picture is being fetched
- **THEN** no picture exists under a final name for it, and a later run fetches
  that picture and writes both its files

#### Scenario: Two runs into one directory
- **WHEN** two downloads run into the same directory at the same time
- **THEN** every picture that appears is complete and matches its sidecar, and
  neither run fails because of the other

### Requirement: Both commands may be run again

Running the download again SHALL NOT fetch a picture that is already present in
the target directory, and SHALL leave what is there untouched. Running the
indexing again SHALL add nothing to the store for a picture it already holds,
because the corpus goes through the same import as any other folder.

#### Scenario: A second download into the same directory
- **WHEN** the download runs again over a directory it already filled
- **THEN** nothing is fetched for the pictures that are there, the run says so,
  and the files are unchanged

#### Scenario: A second indexing of the same corpus
- **WHEN** the indexing runs again over the same directory
- **THEN** no asset is created twice, and the run reports the pictures as
  already stored

### Requirement: The corpus enters the store through the ordinary import

Indexing the demo corpus SHALL use the same import a folder of pictures uses:
the same acceptance rules, the same storage, the same duplicate rule and the
same queued work. The demo corpus SHALL NOT have a path into the store of its
own.

Because the duplicate rule is the content hash and it is global, a picture of
the corpus whose bytes are already stored SHALL be reported as already stored,
and the asset that holds those bytes SHALL NOT be changed: neither its tags nor
its metadata SHALL be rewritten from the corpus, and the provenance the corpus
carries SHALL therefore be recorded only on the assets this import creates.
This is the ordinary import's rule, and the demo corpus SHALL NOT make an
exception to it.

One operator action SHALL carry the corpus from nothing to searchable: fetch,
import, and wait for the queued work to finish.

#### Scenario: A demo asset the import created
- **WHEN** a picture of the corpus is imported into a store that does not hold
  those bytes
- **THEN** the asset carries the tags and the provenance its sidecar gave it,
  and is in every other respect an imported asset

#### Scenario: A picture whose bytes are already stored
- **WHEN** a picture of the corpus is imported into a store that already holds
  those bytes, whatever they were imported or uploaded as
- **THEN** no second asset is created, the existing asset's tags and metadata
  are unchanged, and the run reports the picture as already stored

#### Scenario: One action produces a searchable corpus
- **WHEN** the operator runs the single action that prepares the demo
- **THEN** it ends with the corpus stored and its indexing work finished, so a
  search finds those pictures
