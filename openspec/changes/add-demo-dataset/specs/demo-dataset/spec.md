## Purpose

The corpus the service can be demonstrated on: where its pictures come from,
which of them may be taken, what is recorded about each one, what bounds the
fetching, and what running the commands again is promised to do.

## ADDED Requirements

### Requirement: The demo corpus comes from one named, recorded source

The service SHALL fetch its demo corpus from a single public dataset, named in
the repository's documentation together with the licence of its pictures and of
its annotations. The dataset SHALL NOT be chosen at runtime, and no command
SHALL fetch pictures from a host the documentation does not name.

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

Tags SHALL be normalised to what the service accepts, and a label that cannot
become an acceptable tag SHALL be dropped rather than making the picture
unusable.

#### Scenario: A picture with labels
- **WHEN** a picture the dataset labels is written
- **THEN** its tags are those labels, normalised as the service normalises any
  tag, and its provenance names the dataset, the identifier, the licence and
  the address

#### Scenario: A field the dataset does not have
- **WHEN** the dataset records no author for a picture
- **THEN** the provenance carries no author key, and the documentation says
  attribution is by address

#### Scenario: A label that is not an acceptable tag
- **WHEN** a label cannot be normalised into a tag the service would accept
- **THEN** that label is dropped, the rest are kept, and the picture is still
  written

### Requirement: The download is bounded in every direction

The command SHALL take the number of pictures to fetch, with a documented
default, and SHALL stop at it. Every request SHALL carry a timeout, SHALL be
refused rather than followed when it is answered with a redirect to another
host, and SHALL be abandoned when the response grows past the size the service
accepts for a picture. The archive the manifest arrives in SHALL be read for
the one member the command needs, by exact name, and SHALL be refused when that
member is absent or larger than the bound the command sets.

A response that is not the picture it was supposed to be SHALL be discarded
rather than written: the bytes SHALL be accepted only if they decode as a
picture the service would accept.

#### Scenario: The count is honoured
- **WHEN** a download of a given number of pictures is requested
- **THEN** no more than that many pictures are written, and the run says how
  many it wrote

#### Scenario: A response that grows past the bound
- **WHEN** a picture's response exceeds the size a picture may have
- **THEN** the download of that picture is abandoned, nothing is left behind
  for it, and the run continues with the next one

#### Scenario: A redirect away from the named host
- **WHEN** a request is answered with a redirect to another host
- **THEN** it is not followed, that picture is counted as refused, and the run
  continues

#### Scenario: An archive without the member it must hold
- **WHEN** the manifest archive does not contain the member the command needs,
  or that member is larger than the bound
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
own, and its pictures SHALL be distinguishable afterwards only by the
provenance recorded on them.

One operator action SHALL carry the corpus from nothing to searchable: fetch,
import, and wait for the queued work to finish.

#### Scenario: A demo asset beside an imported one
- **WHEN** a picture of the demo corpus and the same picture imported from a
  folder are compared in the store
- **THEN** they differ only in the metadata that records where each came from

#### Scenario: One action produces a searchable corpus
- **WHEN** the operator runs the single action that prepares the demo
- **THEN** it ends with the corpus stored and its indexing work finished, so a
  search finds those pictures
