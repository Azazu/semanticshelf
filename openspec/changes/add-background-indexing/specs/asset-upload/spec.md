## MODIFIED Requirements

### Requirement: An asset exists whole or not at all

An asset SHALL consist of its original bytes, a thumbnail, a row and the work
that will give it its vectors, and the service SHALL create them in an order
that never leaves a row pointing at a file that is not there: both files SHALL
be in place before the row is written, and a failure to write the row SHALL
remove them. The work SHALL be created in the same transaction as the row, so
an asset never exists without it. A thumbnail that cannot be produced SHALL
fail the upload. A crash between the files and the row MAY leave files with no
row — the only residue the design permits, and one the prune command below
finds.

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

#### Scenario: An asset and its work arrive together
- **WHEN** an asset is stored
- **THEN** the work for every enabled model exists with it, and a failure that
  loses the asset loses that work too
