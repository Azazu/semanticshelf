## 1. Settings, storage and the media root

- [x] 1.1 Add the settings to `app/core/settings.py` with the defaults the requirements fix: media root `.data/media`, maximum upload 20 MiB, maximum pixels 40 000 000, minimum side 32, prune grace 3600 seconds; each validated as positive. Verify: `tests/unit/test_settings_media.py` asserts every default by value, rejects a non-positive value, and reads each one through the environment as well as the constructor.
- [x] 1.2 Write `app/storage.py`: the asset's directory from the first two hex characters of its identifier, the file names from the identifier and the format, an atomic write (temporary name in the target directory, flush, rename), removal of an asset's pair, and a walk over every stored file with its modification time. Verify: `tests/unit/test_storage.py` covers the derived paths, that a written file appears only under its final name, that removal tolerates a missing file, and that the walk finds what the writer wrote.
- [x] 1.3 Assert the containment property directly: every path the module derives stays under the resolved media root, for identifiers and formats chosen to escape it. Verify: a parametrised unit test over adversarial values (parent segments, separators, absolute-looking values, a symbolic link in the root) — each either lands under the root or is refused.

## 2. What a client may say about a picture

- [x] 2.1 Write the tag and metadata normalisation (one function pair used by upload and by patch): trim, lower-case, Unicode-normalise, match the pattern, collapse duplicates, bound the count; metadata must be an object within the size and depth bounds, with the size checked on the raw string before it is parsed. Verify: `tests/unit/test_tagging.py` covers case and spacing collapse, the pattern refusal naming the value, the count bound, a non-object, an over-deep value, and the size bound at its boundary — exactly at the bound accepted, one byte over refused — which is where that guard is tested, away from any parser.
- [x] 2.2 Write the original-filename normalisation beside it (design decision 13): Unicode-normalise, drop control characters, take the last segment so no separator or parent segment survives, trim to the stored bound, and return nothing when nothing usable remains. Verify: `tests/unit/test_tagging.py` covers a name with separators, one with parent segments, one with control characters, one over the bound, one that normalises to nothing, and a non-Latin name that must survive intact.
- [x] 2.3 Write the image inspection used at upload: open the file (header only), refuse above the pixel cap before anything is decoded (design decision 3), verify and reopen, read the dimensions, map the format to the stored content type and extension, refuse a format outside the three and a picture under the minimum side. Verify: `tests/unit/test_images.py` builds pictures in memory for each accepted format, a mislabelled one, a refused format, a too-small one, a truncated file, and the pixel-cap boundary — exactly at the cap accepted, one pixel over refused.
- [x] 2.4 Configure Pillow's own decompression guard from the maximum-pixels setting when the application starts, as the second line behind task 2.3. Verify: a unit test asserts the value after the application factory runs, and states in a comment why it is not the enforcing check.

## 3. Bounding the request itself

- [x] 3.1 Write the body-size middleware (design decision 2): it counts the bytes of the request stream as they arrive and answers 413 problem details when the configured limit is passed, without trusting any declared length. It is the only bound on the uploaded file's size, because the installed parser does not bound a file part. Verify: `tests/api/test_body_limit.py` sends an oversized single file, a body made oversized by several parts each under the limit, one with no declared length (chunked), and one whose declared length understates it; each answers 413 as problem details, and a body under the limit is untouched.
- [x] 3.2 The upload endpoint parses the multipart body itself instead of taking an injected file parameter, with the bounds the parser does enforce: `max_part_size` set to a small multiple of the metadata bound — far enough above it that the application's own bound stays reachable and testable (design decision 2) — and `max_files` and `max_fields` set low, so a request cannot arrive with a thousand parts. A parser refusal stays the framework's 400 — a malformed body is a bad request, and the project's handler already renders it as problem details with the parser's message — while the refusals only the endpoint can judge are its own. Verify: api tests for a metadata field beyond the parser's bound, for one between the two bounds (refused by the application at the size the requirement names), for more file parts than allowed and for more fields than allowed, each asserting the status and the message; the first asserts the parser-stage refusal specifically (400 with the parser's own message, not the application's 422), so the two guards are told apart without touching either setting; and one test uploads a picture well over the parser's 1 MiB default part size normally, which is the evidence that a file part is not bounded there.

## 4. Upload

- [x] 4.1 Write `app/schemas/assets.py`: the asset representation, the listing page, the patch body (absent and null distinguished through the fields the request carries), and the problem body that names an existing asset. Verify: unit tests for the patch body's two cases and for the representation's field set.
- [x] 4.2 Write the upload flow in `app/services/assets.py`: take the parsed parts, read the file in chunks while hashing, look for an existing asset with that hash, inspect the picture, write the original and the thumbnail, insert the row, and remove both files if anything after the writes fails. Verify: the api tests of task 4.4 and the integration test of task 4.5.
- [x] 4.3 Write the router for POST to the assets collection in `app/api/assets.py` and mount it: 201 with the representation and a Location header, and the problem answers 413, 415, 422 and 409 with the existing asset's identifier. The multipart contract of design decision 14 lives here — exactly one file part, tags as repeated fields or one comma-separated field, metadata as a JSON-object string. Verify: the api tests below assert each status and body.
- [x] 4.4 Write `tests/api/test_asset_upload.py` against a temporary media root (the refusals, which never reach the database, so they run in `make check`; the successful paths need a store and live in `tests/integration/test_asset_upload.py`): a picture of each accepted format, a mislabelled one, a file that is not a picture, one under the minimum side, one over the pixel cap, invalid tags, invalid metadata, a duplicate answering 409 while leaving one asset, no file part, two file parts, tags in both accepted forms, and a filename full of separators and control characters whose stored value is clean. Verify: `make check` green; each case asserts both the answer and what is on disk.
- [x] 4.5 Write the integration test for the race: two identical uploads processed concurrently against the real database leave exactly one asset, one 201, one 409, and no file that the surviving asset does not own. Verify: `make test-integration` green.

## 5. Reading an asset

- [x] 5.1 Read one asset by identifier (200 and 404) and serve its bytes and its thumbnail: streamed from disk, detected content type, disposition naming the identifier, private cache lifetime, entity tag from the content hash. Verify: api tests assert the headers and that the body equals the stored bytes.
- [x] 5.2 A file missing from storage answers 404 with a warning in the log, never a server error. Verify: an api test removes the file behind an asset and asserts the status, the problem body and the logged warning.
- [x] 5.3 Listing: newest first with the identifier as tie-break, default and maximum page size, maximum offset, the tag filters and the source filter, `has_more` from one extra row, no total. Verify: an api test pages through more assets than one page holds and asserts each appears exactly once; a test asserts 422 for a page size over the maximum; the filter cases assert the exact set returned.

## 6. Changing and removing an asset

- [ ] 6.1 Partial update of tags and metadata with the normalisation of task 2.1: an omitted field untouched, an explicit null clearing the metadata, and no path by which the picture's own fields can change. Verify: api tests for each case, including an invalid tag leaving the asset untouched.
- [ ] 6.2 Deletion: the row and everything derived from it in one transaction, both files removed after the commit, a failed unlink logged as a warning and the request still successful, the second delete answering 404. Verify: api tests for the three cases, and an integration test that the embeddings of a deleted asset are gone.

## 7. Readiness and orphans

- [ ] 7.1 Add the `media` check to `app/services/readiness.py`: the root exists, is a directory and is writable, asked of the operating system in a thread, run beside the database check rather than after it, and reported without quoting the path. Verify: unit tests with a temporary directory for ok, missing, not-a-directory and not-writable, and a timing test that the probe still answers within about twice the budget.
- [ ] 7.2 Update every test that asserts the exact `checks` body so it expects four entries, and the probe's description in the router. Verify: `make check` and `make test-integration` green.
- [ ] 7.3 Add `storage prune` to `app/cli.py`: take the exclusive advisory lock uploads hold in shared form and stop without changing anything when it cannot be taken (design decision 12); otherwise report files with no asset row and assets whose files are missing, ignoring files younger than the grace period and saying how many were ignored for that reason; with the apply flag remove the orphan files and mark the indexing work of an asset whose file is gone as failed with a reason naming the missing file. Verify: `uv run semanticshelf storage prune --help` recorded in the commit body.
- [ ] 7.4 Write the integration tests for prune: an orphan file and an asset with a removed file are both reported; a dry run changes nothing; the apply run removes the file and marks the job. Verify: `make test-integration` green.
- [ ] 7.5 Take the shared advisory lock in the upload flow: the transaction opens before the first file is written and commits after the row, so the lock covers the whole write and is released by the commit, the rollback or a dropped connection. Verify: an integration test asserts the lock is held while the files are being written and gone afterwards.
- [ ] 7.6 Write the integration test the lock exists for: an upload held between its renames and its row on a hook the test releases only after prune has finished — no time bound anywhere in the test — while prune runs with the apply flag. Prune must change nothing and say an upload is in flight; the upload must complete with both files in place. Verify: `make test-integration` green, and the failing input of task 8.23.

## 8. Failing inputs (high tier: one per new check)

One row per new guard, one probe per row, and each probe removes exactly that
guard — nothing else — runs the named test, records the output in the commit
body and restores the code. Where two guards refuse the same input, the test
distinguishes them by which refusal it observes, so removing one is visible
even though the other still refuses.

| New check | Probe |
|---|---|
| Whole-body byte bound, the only bound on file bytes | 8.1 |
| Parser bound on the metadata part, before it is parsed | 8.2 |
| Parser bound on the number of file parts | 8.3 |
| Parser bound on the number of fields | 8.4 |
| Exactly one file part | 8.5 |
| Format allowlist | 8.6 |
| Pixel cap at the number it names | 8.7 |
| Minimum side | 8.8 |
| Tag pattern | 8.9 |
| Tag count | 8.10 |
| Metadata must be an object | 8.11 |
| Metadata size bound | 8.12 |
| Metadata depth bound | 8.13 |
| Filename: separators and parent segments | 8.14 |
| Filename: control characters | 8.15 |
| Filename: length bound | 8.16 |
| Path containment under the media root | 8.17 |
| Both files before the row | 8.18 |
| Files removed when the row fails | 8.19 |
| Thumbnail re-encoded rather than copied | 8.20 |
| Duplicate refused before any write | 8.21 |
| Unique violation translated to 409 | 8.22 |
| Prune's lock against an upload in flight | 8.23 |
| Prune's grace margin | 8.24 |
| Media check not quoting the path | 8.25 |
| `has_more` from an extra row | 8.26 |
| Missing file answering 404, not a server error | 8.27 |

- [ ] 8.1 Remove the body-size middleware: the oversized-body tests fail, including the one made oversized by extra parts.
- [ ] 8.2 Remove `max_part_size` from the endpoint's parser call, leaving the application's own metadata bound in place: the oversized-metadata test fails because the refusal now comes from the later check — the test asserts the parser-stage refusal specifically and that the metadata parser was never reached, so the two guards are told apart.
- [ ] 8.3 Raise `max_files` beyond what the endpoint accepts: the test that a request with many file parts is refused at the parser fails.
- [ ] 8.4 Raise `max_fields` beyond what the endpoint accepts: the many-fields test fails.
- [ ] 8.5 Remove the check that exactly one file part is present: the no-file and two-file tests fail.
- [ ] 8.6 Remove the format allowlist: the refused-format test fails.
- [ ] 8.7 Remove the header pixel check, leaving Pillow's guard: the cap-plus-one test fails, which is the evidence that the library's guard alone does not enforce the cap.
- [ ] 8.8 Remove the minimum-side check: the too-small test fails.
- [ ] 8.9 Remove the tag pattern check: the invalid-tag test fails.
- [ ] 8.10 Remove the tag count bound: the too-many-tags test fails.
- [ ] 8.11 Remove the check that metadata is an object: the non-object test fails.
- [ ] 8.12 Remove the application's metadata size bound, changing nothing else: its boundary unit test from task 2.1 fails, and so does the api test for a value between the two bounds.
- [ ] 8.13 Remove the metadata depth bound: the over-deep test fails.
- [ ] 8.14 Remove the last-segment step from the filename normalisation: the separator and parent-segment tests fail.
- [ ] 8.15 Remove the control-character strip: that test fails.
- [ ] 8.16 Remove the length trim: the overlong-filename test fails.
- [ ] 8.17 Build the stored path from the uploaded filename instead of the identifier: the containment test of task 1.3 fails.
- [ ] 8.18 Insert the row before the files: the write-order test fails, showing a row whose file is absent.
- [ ] 8.19 Remove the cleanup after a failed insert: the test that nothing remains after a failed row fails, showing two orphan files.
- [ ] 8.20 Copy the original into the thumbnail instead of re-encoding: the metadata test fails, showing the original's blocks in the thumbnail.
- [ ] 8.21 Remove the duplicate pre-check, leaving the unique constraint: the test that a duplicate writes nothing fails, showing files written before the refusal.
- [ ] 8.22 Remove the translation of the unique violation to 409: the duplicate test fails with a server error instead.
- [ ] 8.23 Remove the advisory lock from prune: the concurrent test of task 7.6 fails, showing an upload that lost its files.
- [ ] 8.24 Remove the grace filter from prune: the margin test fails, showing a young orphan removed.
- [ ] 8.25 Report the path in the media check's reason: the test that the body carries no path fails.
- [ ] 8.26 Remove the extra row from the listing query: the `has_more` test fails on the last page.
- [ ] 8.27 Remove the existence check before the file response: the missing-file test fails with a server error instead of 404.

## 9. Documentation

- [ ] 9.1 Write `docs/how-to/uploading.md`: uploading a picture with curl, what is accepted and what is refused with which answer, where the bytes live, what the thumbnail is, and how to find orphans. Verify: every command in it run in its exact form, output pasted from the run.
- [ ] 9.2 Extend `docs/reference/settings.md` with the five settings and `docs/reference/commands.md` with the prune command; update the layout in `AGENTS.md` with `app/storage.py`, `app/schemas/` and the new service and router. Verify: all four documents re-read whole after the last edit.

## 10. Wrap-up

- [ ] 10.1 Commits per logical block, no agent trailers, each body naming the evidence for the tasks its diff holds. Verify: `git log --format=%B main..HEAD | grep -c '^Co-Authored-By'` prints `0`.
- [ ] 10.2 `env -u DATABASE_URL make check` green and `make test-integration` green against pgvector. Verify: both outputs recorded in a commit body.
- [ ] 10.3 Acceptance on GitHub (the user pushes the branch): both jobs green. Verify: the user reports the run.
- [ ] 10.4 `openspec validate add-asset-upload-and-storage --strict` and `scripts/pregate-verify.sh gate2 add-asset-upload-and-storage` pass; request Gate 2 with `/gate-review add-asset-upload-and-storage 2`.
