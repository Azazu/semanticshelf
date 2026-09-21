## 1. Settings, storage and the media root

- [ ] 1.1 Add the settings to `app/core/settings.py` with the defaults the requirements fix: media root `.data/media`, maximum upload 20 MiB, maximum pixels 40 000 000, minimum side 32, prune grace 3600 seconds; each validated as positive. Verify: `tests/unit/test_settings_media.py` asserts every default by value, rejects a non-positive value, and reads each one through the environment as well as the constructor.
- [ ] 1.2 Write `app/storage.py`: the asset's directory from the first two hex characters of its identifier, the file names from the identifier and the format, an atomic write (temporary name in the target directory, flush, rename), removal of an asset's pair, and a walk over every stored file with its modification time. Verify: `tests/unit/test_storage.py` covers the derived paths, that a written file appears only under its final name, that removal tolerates a missing file, and that the walk finds what the writer wrote.
- [ ] 1.3 Assert the containment property directly: every path the module derives stays under the resolved media root, for identifiers and formats chosen to escape it. Verify: a parametrised unit test over adversarial values (parent segments, separators, absolute-looking values, a symbolic link in the root) — each either lands under the root or is refused.

## 2. What a client may say about a picture

- [ ] 2.1 Write the tag and metadata normalisation (one function pair used by upload and by patch): trim, lower-case, Unicode-normalise, match the pattern, collapse duplicates, bound the count; metadata must be an object within the size and depth bounds, with the size checked on the raw string before it is parsed. Verify: `tests/unit/test_tagging.py` covers case and spacing collapse, the pattern refusal naming the value, the count bound, a non-object, an oversized and an over-deep metadata value.
- [ ] 2.2 Write the original-filename normalisation beside it (design decision 13): Unicode-normalise, drop control characters, take the last segment so no separator or parent segment survives, trim to the stored bound, and return nothing when nothing usable remains. Verify: `tests/unit/test_tagging.py` covers a name with separators, one with parent segments, one with control characters, one over the bound, one that normalises to nothing, and a non-Latin name that must survive intact.
- [ ] 2.3 Write the image inspection used at upload: open the file (header only), refuse above the pixel cap before anything is decoded (design decision 3), verify and reopen, read the dimensions, map the format to the stored content type and extension, refuse a format outside the three and a picture under the minimum side. Verify: `tests/unit/test_images.py` builds pictures in memory for each accepted format, a mislabelled one, a refused format, a too-small one, a truncated file, and the pixel-cap boundary — exactly at the cap accepted, one pixel over refused.
- [ ] 2.4 Configure Pillow's own decompression guard from the maximum-pixels setting when the application starts, as the second line behind task 2.3. Verify: a unit test asserts the value after the application factory runs, and states in a comment why it is not the enforcing check.

## 3. Bounding the request itself

- [ ] 3.1 Write the body-size middleware (design decision 2): it counts the bytes of the request stream as they arrive and answers 413 problem details when the configured limit is passed, without trusting any declared length. It is the only bound on the uploaded file's size, because the installed parser does not bound a file part. Verify: `tests/api/test_body_limit.py` sends an oversized single file, a body made oversized by several parts each under the limit, one with no declared length (chunked), and one whose declared length understates it; each answers 413 as problem details, and a body under the limit is untouched.
- [ ] 3.2 The upload endpoint parses the multipart body itself instead of taking an injected file parameter, with the bounds the parser does enforce: `max_part_size` set to the metadata bound, so an oversized metadata string is refused before it is parsed, and `max_files` and `max_fields` set low, so a request cannot arrive with a thousand parts. A parser refusal becomes 422 problem details naming what was wrong, not the parser's own 400. Verify: api tests for an oversized metadata field, for more file parts than allowed and for more fields than allowed, each asserting the status and the message; and one that a picture well over the parser's 1 MiB default part size uploads normally, which is the evidence that the file part is not bounded there.

## 4. Upload

- [ ] 4.1 Write `app/schemas/assets.py`: the asset representation, the listing page, the patch body (absent and null distinguished through the fields the request carries), and the problem body that names an existing asset. Verify: unit tests for the patch body's two cases and for the representation's field set.
- [ ] 4.2 Write the upload flow in `app/services/assets.py`: take the parsed parts, read the file in chunks while hashing, look for an existing asset with that hash, inspect the picture, write the original and the thumbnail, insert the row, and remove both files if anything after the writes fails. Verify: the api tests of task 4.4 and the integration test of task 4.5.
- [ ] 4.3 Write the router for POST to the assets collection in `app/api/assets.py` and mount it: 201 with the representation and a Location header, and the problem answers 413, 415, 422 and 409 with the existing asset's identifier. The multipart contract of design decision 14 lives here — exactly one file part, tags as repeated fields or one comma-separated field, metadata as a JSON-object string. Verify: the api tests below assert each status and body.
- [ ] 4.4 Write `tests/api/test_asset_upload.py` against a temporary media root: a picture of each accepted format, a mislabelled one, a file that is not a picture, one under the minimum side, one over the pixel cap, invalid tags, invalid metadata, a duplicate answering 409 while leaving one asset, no file part, two file parts, tags in both accepted forms, and a filename full of separators and control characters whose stored value is clean. Verify: `make check` green; each case asserts both the answer and what is on disk.
- [ ] 4.5 Write the integration test for the race: two identical uploads processed concurrently against the real database leave exactly one asset, one 201, one 409, and no file that the surviving asset does not own. Verify: `make test-integration` green.

## 5. Reading an asset

- [ ] 5.1 Read one asset by identifier (200 and 404) and serve its bytes and its thumbnail: streamed from disk, detected content type, disposition naming the identifier, private cache lifetime, entity tag from the content hash. Verify: api tests assert the headers and that the body equals the stored bytes.
- [ ] 5.2 A file missing from storage answers 404 with a warning in the log, never a server error. Verify: an api test removes the file behind an asset and asserts the status, the problem body and the logged warning.
- [ ] 5.3 Listing: newest first with the identifier as tie-break, default and maximum page size, maximum offset, the tag filters and the source filter, `has_more` from one extra row, no total. Verify: an api test pages through more assets than one page holds and asserts each appears exactly once; a test asserts 422 for a page size over the maximum; the filter cases assert the exact set returned.

## 6. Changing and removing an asset

- [ ] 6.1 Partial update of tags and metadata with the normalisation of task 2.1: an omitted field untouched, an explicit null clearing the metadata, and no path by which the picture's own fields can change. Verify: api tests for each case, including an invalid tag leaving the asset untouched.
- [ ] 6.2 Deletion: the row and everything derived from it in one transaction, both files removed after the commit, a failed unlink logged as a warning and the request still successful, the second delete answering 404. Verify: api tests for the three cases, and an integration test that the embeddings of a deleted asset are gone.

## 7. Readiness and orphans

- [ ] 7.1 Add the `media` check to `app/services/readiness.py`: the root exists, is a directory and is writable, asked of the operating system in a thread, run beside the database check rather than after it, and reported without quoting the path. Verify: unit tests with a temporary directory for ok, missing, not-a-directory and not-writable, and a timing test that the probe still answers within about twice the budget.
- [ ] 7.2 Update every test that asserts the exact `checks` body so it expects four entries, and the probe's description in the router. Verify: `make check` and `make test-integration` green.
- [ ] 7.3 Add `storage prune` to `app/cli.py`: take the exclusive advisory lock uploads hold in shared form and stop without changing anything when it cannot be taken (design decision 12); otherwise report files with no asset row and assets whose files are missing, ignoring files younger than the grace period and saying how many were ignored for that reason; with the apply flag remove the orphan files and mark the indexing work of an asset whose file is gone as failed with a reason naming the missing file. Verify: `uv run semanticshelf storage prune --help` recorded in the commit body.
- [ ] 7.4 Write the integration tests for prune: an orphan file and an asset with a removed file are both reported; a dry run changes nothing; the apply run removes the file and marks the job. Verify: `make test-integration` green.
- [ ] 7.5 Take the shared advisory lock in the upload flow: the transaction opens before the first file is written and commits after the row, so the lock covers the whole write and is released by the commit, the rollback or a dropped connection. Verify: an integration test asserts the lock is held while the files are being written and gone afterwards.
- [ ] 7.6 Write the integration test the lock exists for: an upload held between its renames and its row on a hook the test releases only after prune has finished — no time bound anywhere in the test — while prune runs with the apply flag. Prune must change nothing and say an upload is in flight; the upload must complete with both files in place. Verify: `make test-integration` green, and the failing input of task 8.14.

## 8. Failing inputs (high tier: one per new check)

Every new guard this change introduces, and the probe that demonstrates the
test catching its removal. Each probe removes exactly one guard, runs the
named test, records the output in the commit body, and restores the code.

| New check | Probe |
|---|---|
| Whole-body byte bound, including the uploaded file | 8.1 |
| Metadata field bounded by the parser before parsing | 8.2 |
| Part and field counts bounded by the parser | 8.2a |
| Exactly one file part | 8.3 |
| Format allowlist (415) | 8.4 |
| Pixel cap at the number it names | 8.5 |
| Minimum side | 8.6 |
| Tag pattern and count | 8.7 |
| Metadata type, size and depth | 8.8 |
| Original-filename normalisation | 8.9 |
| Path containment | 8.10 |
| Files before row, cleanup on failure | 8.11 |
| Thumbnail re-encoded, not copied | 8.12 |
| Duplicate refused | 8.13 |
| Prune's lock against an upload in flight | 8.14 |
| Prune's grace period | 8.14a |
| Media check leaking the path | 8.15 |
| `has_more` from an extra row | 8.16 |
| Missing file answering 404, not 500 | 8.17 |

- [ ] 8.1 The body-size middleware removed: the oversized-body tests fail.
- [ ] 8.2 The metadata part bound removed from the parser call: the oversized-metadata test fails, showing the value parsed instead of refused.
- [ ] 8.2a The part and field count bounds removed: the too-many-parts tests fail.
- [ ] 8.3 The file-part count check removed: the no-file and two-file tests fail.
- [ ] 8.4 The format allowlist removed: the refused-format test fails.
- [ ] 8.5 The header pixel check removed (leaving only Pillow's guard): the cap-plus-one test fails, which is the evidence that the library's guard alone does not enforce the cap.
- [ ] 8.6 The minimum-side check removed: the too-small test fails.
- [ ] 8.7 The tag pattern and count checks removed: the invalid-tag and too-many-tags tests fail.
- [ ] 8.8 The metadata type, size and depth checks removed: those three tests fail.
- [ ] 8.9 The filename normalisation removed: the separator, control-character and length tests fail.
- [ ] 8.10 The stored path built from the uploaded filename instead of the identifier: the containment test of task 1.3 fails.
- [ ] 8.11 The row inserted before the files: the write-order test fails, showing a row whose file is absent.
- [ ] 8.12 The thumbnail copied from the original instead of re-encoded: the metadata test fails, showing the original's blocks in the thumbnail.
- [ ] 8.13 The duplicate pre-check and the unique-violation translation removed: the duplicate test fails.
- [ ] 8.14 The advisory lock removed from prune: the concurrent test of task 7.6 fails, showing an upload that lost its files to a prune beside it.
- [ ] 8.14a The grace period removed from prune: a file younger than the grace with no row is deleted, which the margin test catches.
- [ ] 8.15 The media check reporting the path in its reason: the test that the body carries no path fails.
- [ ] 8.16 The extra row of the listing removed: the `has_more` test fails on the last page.
- [ ] 8.17 The existence check before the file response removed: the missing-file test fails with a server error instead of 404.

## 9. Documentation

- [ ] 9.1 Write `docs/how-to/uploading.md`: uploading a picture with curl, what is accepted and what is refused with which answer, where the bytes live, what the thumbnail is, and how to find orphans. Verify: every command in it run in its exact form, output pasted from the run.
- [ ] 9.2 Extend `docs/reference/settings.md` with the five settings and `docs/reference/commands.md` with the prune command; update the layout in `AGENTS.md` with `app/storage.py`, `app/schemas/` and the new service and router. Verify: all four documents re-read whole after the last edit.

## 10. Wrap-up

- [ ] 10.1 Commits per logical block, no agent trailers, each body naming the evidence for the tasks its diff holds. Verify: `git log --format=%B main..HEAD | grep -c '^Co-Authored-By'` prints `0`.
- [ ] 10.2 `env -u DATABASE_URL make check` green and `make test-integration` green against pgvector. Verify: both outputs recorded in a commit body.
- [ ] 10.3 Acceptance on GitHub (the user pushes the branch): both jobs green. Verify: the user reports the run.
- [ ] 10.4 `openspec validate add-asset-upload-and-storage --strict` and `scripts/pregate-verify.sh gate2 add-asset-upload-and-storage` pass; request Gate 2 with `/gate-review add-asset-upload-and-storage 2`.
