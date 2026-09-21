# Accept, store and serve pictures

**Risk-Tier:** high

## Why

The schema has held assets since change 3 and the models have produced vectors
since change 4, but nothing can put a picture into the system. This change
opens the door: the first endpoints that accept data from outside the service,
the first bytes written to disk, and the first deletion. Everything after it —
background indexing, both searches, the demo dataset, the UI — needs an asset
to exist.

It is also where the project's sharpest edges are. A picture arrives from a
client, so its format, its size and its pixel count are all claims until the
service checks them; a decompression bomb is a 100 KB file that becomes 40 GB
of pixels. The bytes land on a filesystem, so every path the service touches
must be derived from an identifier it generated, never from anything a client
sent. And two files plus one row must either all exist or leave nothing
behind. Hence tier `high` on three of the project's own triggers at once:
upload, path handling and deletion.

## What Changes

- `POST /api/v1/assets`: multipart upload with the format detected from the
  bytes rather than from the filename or the part header; the size limit
  enforced while reading, before anything is decoded; the pixel cap applied
  before pixels are allocated; deduplication by content hash; the original
  stored unchanged and a thumbnail re-encoded from the decoded pixels, so no
  metadata block of the original is carried into it.
- The write order that makes an asset whole: both files renamed into place,
  then the row; a failed insert removes the files. A crash between them can
  only leave orphan files, never a row pointing at nothing.
- `GET /api/v1/assets/{id}`, `/file`, `/thumbnail`: the representation, and
  the bytes streamed from disk with caching headers and the content hash as
  the entity tag. Files are never loaded into memory to be served.
- `GET /api/v1/assets`: listing with tag filters, source, pagination by
  `limit`/`offset` and `has_more` computed by fetching one extra row.
- `PATCH /api/v1/assets/{id}`: tags and metadata by merge-patch semantics; the
  file is immutable.
- `DELETE /api/v1/assets/{id}`: the row and everything derived from it in one
  transaction, the two files removed after the commit, a failed unlink logged
  and left to `storage prune`.
- Tag and metadata rules (FR-TAG-1, FR-TAG-2) as one normalisation used by
  both upload and patch.
- `semanticshelf storage prune [--apply]`: orphan files and assets whose files
  are gone; it changes nothing without `--apply`.
- Readiness gains its fourth check: the media root exists and is writable.
- New settings: `MEDIA_ROOT`, `MAX_UPLOAD_BYTES`, `MAX_IMAGE_PIXELS`,
  `MIN_IMAGE_SIDE`.

### Deliberately not in this change, and why

- `index_status` in the asset representation and `index_status=<model>:<status>`
  in the listing (both named in FR-AST-8 and FR-AST-10) arrive with the jobs
  they report on, in change 6. A field that would be an empty map in every
  response is not a feature.
- `links.similar` (FR-AST-8) arrives with the endpoint it points at, in
  change 11. A link to a 404 is worse than no link.
- `GET /api/v1/tags` (FR-TAG-3) belongs to change 8, which the roadmap already
  assigns it to; the tag **rules** it depends on are established here.

## Capabilities

### New Capabilities

- `asset-upload`: what happens when a picture arrives — what is accepted, what
  is refused and with which answer, what is stored, and what state is possible
  after a crash.
- `asset-api`: the resource surface of an asset once it exists — reading it,
  serving its bytes, listing, changing its tags and metadata, deleting it.

### Modified Capabilities

- `health-probes`: readiness gains the media-root check, so the requirement's
  check list and its ready body change.

## Non-goals

- Perceptual deduplication. Identical bytes are one asset; a re-encoded or
  resized copy is a different asset, as FR-AST-4 states.
- Any form of authentication or per-client authorization. The service is
  single-tenant and unauthenticated by design (§6); adding a user model here
  would be scope no requirement asks for.
- Serving anything by path. Nothing under the media root is reachable except
  through an endpoint that resolves an id.
- Image transformations beyond the one thumbnail: no resizing on request, no
  format conversion, no EXIF rotation of the stored original (the original is
  stored unchanged, by requirement).
- Enqueueing indexing work. Upload creates an asset; the jobs that embed it
  are change 6, and until then an asset simply has no vectors.
- Background or deferred thumbnailing. The thumbnail is part of the upload, so
  that an asset is never half-created.

## Impact

- New: `app/schemas/` (request and response models), `app/api/assets.py`,
  `app/services/assets.py`, `app/storage.py` (the only module that builds a
  filesystem path), `app/media.py`-level image decoding inside the upload
  service, `storage prune` in `app/cli.py`.
- Changed: `app/core/settings.py` (four settings), `app/services/readiness.py`
  and `app/api/health.py` (the fourth check), `app/main.py` (the router),
  `docs/reference/settings.md`, `docs/reference/commands.md`, a new how-to for
  uploading and storage, the AGENTS.md layout.
- Unchanged: the schema. Change 3 created the table this change finally fills;
  no migration is needed, and none is written.
- Data: the first bytes the service owns. `MEDIA_ROOT` defaults to `.data/media`,
  which is gitignored, and the tests use a temporary directory.
