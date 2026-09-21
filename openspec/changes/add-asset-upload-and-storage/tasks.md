## 1. Settings, storage and the decoder's guard

- [ ] 1.1 Add the four settings to `app/core/settings.py` with the defaults the requirements fix: media root `.data/media`, maximum upload 20 MiB, maximum pixels 40 000 000, minimum side 32; each validated as positive. Verify: `tests/unit/test_settings_media.py` asserts every default by value and rejects a non-positive value, and reads the media root through the environment as well as the constructor.
- [ ] 1.2 Write `app/storage.py`: the asset's directory from the first two hex characters of its identifier, the file names from the identifier and the format, an atomic write (temporary name in the target directory, flush, rename), removal of an asset's pair, and a walk over every stored file. Verify: `tests/unit/test_storage.py` covers the derived paths, that a written file appears only under its final name, that removal tolerates a missing file, and that the walk finds what the writer wrote.
- [ ] 1.3 Assert the containment property directly: every path the module derives stays under the resolved media root, for identifiers and formats chosen to escape it. Verify: a parametrised unit test over adversarial values (parent segments, separators, absolute-looking values, a symbolic link in the root) — each either lands under the root or is refused.
- [ ] 1.4 Configure the decoder's decompression guard from the maximum-pixels setting when the application starts, and nowhere else. Verify: a unit test asserts the value is applied after the application factory runs, and the failing input of task 8.2 covers its removal.

## 2. What a client may say about a picture

- [ ] 2.1 Write the tag and metadata normalisation (one function pair used by upload and by patch): trim, lower-case, Unicode-normalise, match the pattern, collapse duplicates, bound the count; metadata must be an object within the size and depth bounds. Verify: `tests/unit/test_tagging.py` covers case and spacing collapse, the pattern refusal naming the value, the count bound, a non-object, an oversized and an over-deep metadata value.
- [ ] 2.2 Write the image inspection used at upload: detect the format from the bytes, verify and reopen, read the dimensions, map the format to the stored content type and extension, refuse a format outside the three and a picture under the minimum side. Verify: `tests/unit/test_images.py` builds pictures in memory for each accepted format, a mislabelled one, a refused format, a too-small one and a truncated file.

## 3. Upload

- [ ] 3.1 Write `app/schemas/assets.py`: the asset representation, the listing page, the patch body (absent and null distinguished through the fields the request carries), and the problem body that names an existing asset. Verify: unit tests for the patch body's two cases and for the representation's field set.
- [ ] 3.2 Write the upload flow in `app/services/assets.py`: read the part in chunks while hashing and counting, refuse over the byte limit, look for an existing asset with that hash, inspect the picture, write the original and the thumbnail, insert the row, and remove both files if anything after the writes fails. Verify: the api tests of task 3.4 and the integration test of task 3.5.
- [ ] 3.3 Write the router for POST to the assets collection in `app/api/assets.py` and mount it in the application: 201 with the representation and a Location header, and the problem answers 413, 415, 422 and 409 with the existing asset's identifier. Verify: the api tests below assert each status and body.
- [ ] 3.4 Write `tests/api/test_asset_upload.py` against a temporary media root: a picture of each accepted format, a mislabelled one, a file that is not a picture, one over the byte limit, one under the minimum side, one over the pixel cap, invalid tags, invalid metadata, and the duplicate answering 409 while leaving one asset. Verify: `make check` green; each case asserts both the answer and what is on disk.
- [ ] 3.5 Write the integration test for the race: two identical uploads processed concurrently against the real database leave exactly one asset, one 201, one 409, and no file that the surviving asset does not own. Verify: `make test-integration` green.

## 4. Reading an asset

- [ ] 4.1 Read one asset by identifier (200 and 404) and serve its bytes and its thumbnail: streamed from disk, detected content type, disposition naming the identifier, private cache lifetime, entity tag from the content hash. Verify: api tests assert the headers and that the body equals the stored bytes.
- [ ] 4.2 A file missing from storage answers 404 with a warning in the log, never a server error. Verify: an api test removes the file behind an asset and asserts the status, the problem body and the logged warning.
- [ ] 4.3 Listing: newest first with the identifier as tie-break, default and maximum page size, maximum offset, the tag filters and the source filter, `has_more` from one extra row, no total. Verify: an api test pages through more assets than one page holds and asserts each appears exactly once; a test asserts 422 for a page size over the maximum; the filter cases assert the exact set returned.

## 5. Changing and removing an asset

- [ ] 5.1 Partial update of tags and metadata with the normalisation of task 2.1: an omitted field untouched, an explicit null clearing the metadata, and no path by which the picture's own fields can change. Verify: api tests for each case, including an invalid tag leaving the asset untouched.
- [ ] 5.2 Deletion: the row and everything derived from it in one transaction, both files removed after the commit, a failed unlink logged as a warning and the request still successful, the second delete answering 404. Verify: api tests for the three cases, and an integration test that the embeddings of a deleted asset are gone.

## 6. Readiness knows about storage

- [ ] 6.1 Add the `media` check to `app/services/readiness.py`: the root exists, is a directory and is writable, asked of the operating system in a thread, run beside the database check rather than after it, and reported without quoting the path. Verify: unit tests with a temporary directory for ok, missing, not-a-directory and not-writable, and a timing test that the probe still answers within about twice the budget.
- [ ] 6.2 Update every test that asserts the exact `checks` body so it expects four entries, and the probe's description in the router. Verify: `make check` and `make test-integration` green.

## 7. Orphans

- [ ] 7.1 Add `storage prune` to `app/cli.py`: report files with no asset row and assets whose files are missing; with the apply flag remove the orphan files and mark the indexing work of an asset whose file is gone as failed with a reason naming the missing file. Verify: `uv run semanticshelf storage prune --help` recorded in the commit body.
- [ ] 7.2 Write the integration test: an orphan file and an asset with a removed file are both reported; a dry run changes nothing; the apply run removes the file and marks the job. Verify: `make test-integration` green.

## 8. Failing inputs (high tier: one per new check)

- [ ] 8.1 The byte limit removed: the oversized-upload test fails. Verify: output recorded in the commit body, code restored.
- [ ] 8.2 The decoder's guard not configured: the pixel-cap test fails and the oversized picture decodes. Verify: output recorded, code restored.
- [ ] 8.3 The stored path built from the uploaded filename instead of the identifier: the containment test of task 1.3 fails. Verify: output recorded, code restored.
- [ ] 8.4 The row inserted before the files: the write-order test fails, showing a row whose file is absent. Verify: output recorded, code restored.
- [ ] 8.5 The thumbnail copied from the original instead of re-encoded: the metadata test fails, showing the original's blocks in the thumbnail. Verify: output recorded, code restored.
- [ ] 8.6 The duplicate pre-check and the unique violation both removed: the duplicate test fails. Verify: output recorded, code restored.
- [ ] 8.7 The media check reporting the path in its reason: the test that the body carries no path fails. Verify: output recorded, code restored.
- [ ] 8.8 The extra row of the listing removed: the `has_more` test fails on the last page. Verify: output recorded, code restored.

## 9. Documentation

- [ ] 9.1 Write `docs/how-to/uploading.md`: uploading a picture with curl, what is accepted and what is refused with which answer, where the bytes live, what the thumbnail is, and how to find orphans. Verify: every command in it run in its exact form, output pasted from the run.
- [ ] 9.2 Extend `docs/reference/settings.md` with the four settings and `docs/reference/commands.md` with the prune command; update the layout in `AGENTS.md` with `app/storage.py`, `app/schemas/` and the new service and router. Verify: all four documents re-read whole after the last edit.

## 10. Wrap-up

- [ ] 10.1 Commits per logical block, no agent trailers, each body naming the evidence for the tasks its diff holds. Verify: `git log --format=%B main..HEAD | grep -c '^Co-Authored-By'` prints `0`.
- [ ] 10.2 `env -u DATABASE_URL make check` green and `make test-integration` green against pgvector. Verify: both outputs recorded in a commit body.
- [ ] 10.3 Acceptance on GitHub (the user pushes the branch): both jobs green. Verify: the user reports the run.
- [ ] 10.4 `openspec validate add-asset-upload-and-storage --strict` and `scripts/pregate-verify.sh gate2 add-asset-upload-and-storage` pass; request Gate 2 with `/gate-review add-asset-upload-and-storage 2`.
