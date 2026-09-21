# Review — add-asset-upload-and-storage

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-21
**Reviewed-Commit:** 592752c1718fc4346535486155c8ba14bc223d1e
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | blocker | `design.md` Applicability / Decisions 4 and `specs/asset-upload/spec.md` “Orphan files are findable and removable” | The write order exposes both final filenames before the asset row exists, while `storage prune --apply` deletes every final file without a row. A prune concurrent with a normal upload can therefore classify the in-flight files as orphans, unlink them, and then allow the upload transaction to commit a row whose files are missing—the state the design says is impossible. The concurrent-writers analysis covers only duplicate uploads. Specify a synchronization or safe-age/provenance mechanism and add a concurrent upload/prune verification that preserves the whole-asset invariant. | fixed |
| 2 | blocker | `design.md` Decision 2; `tasks.md` 3.2–3.4 | Counting chunks after FastAPI has produced an `UploadFile` does not enforce the limit while the request is read: the installed FastAPI/Starlette stack parses the complete multipart request and spools file parts before endpoint code receives them. It also bounds only the selected file, not the whole multipart body required by NFR-SEC-5, so extra parts/overhead can remain unbounded. Name a parser/request-stream mechanism that aborts an untrusted chunked request without relying on `Content-Length`, maps it to 413 problem details, and verify both over-limit file and whole-body/extra-part cases. | fixed |
| 3 | blocker | `design.md` Decision 3; `tasks.md` 1.4, 2.2, 8.2 | Setting Pillow's `Image.MAX_IMAGE_PIXELS` to the configured cap does not enforce that cap: Pillow 12.3 emits `DecompressionBombWarning` for pixel counts just above the value and raises only above twice the value. Thus a 40,000,001-pixel image can continue to decoding even though FR-AST-3 requires 422 above 40,000,000. Define the exact rejection mechanism before pixel allocation (including warning handling or an explicit header-dimension check) and add boundary evidence at the cap and cap+1; the failing-input task must exercise that exact guard. | fixed |
| 4 | major | `specs/asset-upload/spec.md` “Stored paths are derived, never supplied”; `tasks.md` sections 2–3 | The delta requires the recorded original filename to be bounded and stripped of control characters and path separators, but no implementation task owns that normalization and no verification covers the recorded value for separators, parent segments, controls, or overlength input. Task 1.3 tests generated path components, not the client filename stored in metadata. Add explicit implementation and verification coverage for the full filename contract. | fixed |
| 5 | major | `tasks.md` 3.2–3.4; `docs/explanation/requirements.md` FR-AST-1 | The upload tasks do not cover the multipart input contract: exactly one required `file`, tags accepted as either repeated fields or comma-separated values, and `meta` parsed from a JSON-object string bounded before processing. Without implementation and API-test tasks for those forms and their malformed/duplicate/absent cases, the proposal's endpoint scope lacks the implementation-plus-verification coverage required at Gate 1. | fixed |
| 6 | major | `tasks.md` section 8 | The high-tier failing-input plan is not one-per-new-check as its heading claims. It omits, among others, unsupported-format rejection, minimum-side rejection, tag pattern/count checks, and metadata type/size/depth checks introduced by tasks 2.1–2.2. Ordinary positive/rejection tests in tasks 2–3 do not provide the required evidence that each guard's test fails when that guard is removed. Add failing-input evidence tasks for every new validation guard (or consolidate them with an explicit exhaustive mapping). | fixed |

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-21
**Reviewed-Commit:** aaf341b07622894b26324b7f3f385cea6fed0d10
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | changes-requested — The fixed grace period reduces the race but does not preserve the claimed invariant: no bound prevents an upload from remaining between rename and commit past `PRUNE_MIN_AGE_SECONDS`, after which prune may delete its files. Task 7.5 exercises only a still-young upload. Specify synchronization, active-upload provenance, or another mechanism that remains safe for an arbitrarily delayed in-flight upload, and make the concurrent test cover that safety property. |
| 2 | changes-requested — The proposed parser mechanism does not enforce the stated file-part bound on the installed Starlette 1.6.0 stack: `MultiPartParser.on_part_data` applies `max_part_size` only when the part is not a file and appends file data without that check. Consequently tasks 3.2 and 8.2 cannot verify the claimed file guard. The whole-body middleware is the effective bound, but task 3.1 also does not explicitly exercise a multipart body made oversized by extra parts as requested. Revise the mechanism and tests to match the installed parser behavior. |
| 3 | confirmed — Decision 3 now defines an explicit header-dimension comparison before decode, tasks 2.3 and 8.5 cover removal of that exact guard, and the acceptance boundary is specified at the cap and cap plus one. |
| 4 | confirmed — Decision 13 and task 2.2 now assign filename normalization and cover separators, parent segments, controls, the stored bound, an empty result, and preserved non-Latin text; task 4.4 verifies the recorded API value. |
| 5 | confirmed — Decision 14, the added upload requirement, and tasks 2.1, 4.3, and 4.4 now assign and verify the required/duplicate file cases, both tag forms, and bounded JSON-object metadata parsing. |
| 6 | changes-requested — The new mapping covers the guards originally named, but it is still not exhaustive for the revised plan: task 3.2 newly requires bounded file and field counts, yet no failing-input probe covers `max_fields` (or independently demonstrates the parser's file-count bound), and probe 8.2 targets a file-size check that `max_part_size` does not perform. Update the exhaustive mapping and probes after correcting finding 2. |

## Confirmation 2 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-21
**Reviewed-Commit:** 928b30661e6dbcbe6b6e8ab77b4312a05dd105a8
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — Decision 12 now serialises upload and prune with shared/exclusive transaction-scoped advisory locks, without a time assumption. Tasks 7.5–7.6 verify lock lifetime and hold an upload between rename and commit until a non-waiting prune has finished, so prune changes nothing while the whole-asset invariant is exposed. |
| 2 | confirmed — Decision 2 now matches Starlette 1.6.0: `max_part_size` applies only to non-file parts, while the ASGI middleware is the sole file and whole-body byte bound. Tasks 3.1–3.2 cover an oversized file, aggregate extra-part overhead, absent or understated length, parser part counts, and the parser's actual file-part behavior. |
| 3 | confirmed — The explicit header-dimension comparison remains the enforcing guard before decode, with exact-cap and cap-plus-one verification in task 2.3 and removal of that guard in probe 8.5. |
| 4 | confirmed — Decision 13 and tasks 2.2, 4.4, and 8.9 assign implementation, API verification, and failing-input evidence for separators, parent segments, controls, the stored bound, empty results, and preserved non-Latin text. |
| 5 | confirmed — Decision 14 and tasks 2.1, 3.2, 4.3, and 4.4 cover exactly one required file, both tag forms, bounded JSON-object metadata, parser limits, and malformed, duplicate, and absent input cases. |
| 6 | changes-requested — The mapping now names the omitted validation families, but it still does not provide one independently demonstrated failing input per new check. Probes 8.2a, 8.7, and 8.8 each remove multiple distinct guards despite the section's rule that each probe removes exactly one; the same issue appears in 8.13. In addition, removing only the parser's metadata `max_part_size` cannot make the stated oversized-metadata refusal test fail, because task 2.1 independently rejects the same raw value at the metadata-size bound before JSON parsing. Split the grouped guards into independently removed probes and make 8.2 observe the parser-stage bound specifically (for example, by proving the downstream metadata parser is not reached). |

## Confirmation 3 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-21
**Reviewed-Commit:** 14c0d54985c195a151795666526ab95ba796aaa5
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — The transaction-scoped shared/exclusive advisory lock remains the invariant-preserving mechanism, and tasks 7.5–7.6 verify its lifetime and the upload/prune race without relying on an upload-duration bound. |
| 2 | confirmed — The ASGI middleware is the sole file and whole-body byte bound, while the endpoint uses only the multipart limits Starlette actually enforces; tasks 3.1–3.2 cover oversized files, aggregate extra-part overhead, absent or understated length, parser part counts, and parser-stage metadata refusal. |
| 3 | confirmed — The explicit header-dimension check rejects cap-plus-one before decoding, with exact-cap boundary coverage and a failing-input probe that removes only that check while leaving Pillow's weaker guard in place. |
| 4 | confirmed — Filename normalisation has explicit implementation, API, and independently split failing-input coverage for path segments and separators, controls, and the stored length bound, including an unusable result and preserved non-Latin text. |
| 5 | confirmed — The endpoint and parser tasks implement and verify exactly one required file, both tag encodings, bounded JSON-object metadata, and the malformed, duplicate, absent, and excessive-part cases. |
| 6 | changes-requested — The grouped probes identified in Confirmation 2 are now split, and probe 8.2 distinguishes the parser-stage metadata refusal from the application guard. However, probe 8.12 still violates the section's explicit one-guard rule: it removes the application metadata-size bound **and** raises the parser bound. Give the application metadata-size guard a test below the parser limit or exercise it directly at the normalisation boundary, so its probe changes only that guard. |

## Confirmation 4 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-21
**Reviewed-Commit:** 34b3cf71e09d2d7cf1d9b10daf49c8e2ad0a90ab
**Verdict:** confirmed

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — The shared/exclusive transaction-scoped advisory-lock design and its unbounded-delay integration test still prevent prune from acting while an upload is between its file writes and row commit. |
| 2 | confirmed — The ASGI middleware remains the sole whole-body and file-byte bound, while the parser is assigned only field-size and part-count limits that Starlette enforces; the planned tests distinguish each refusal stage. |
| 3 | confirmed — The explicit header-dimension comparison still enforces the configured pixel cap before decode at the exact cap/cap-plus-one boundary, independently of Pillow's weaker guard. |
| 4 | confirmed — Filename normalisation still has explicit implementation, API, and one-guard failing-input coverage for separators and parent segments, controls, and the stored length bound. |
| 5 | confirmed — The multipart contract still assigns and verifies exactly one required file, both tag encodings, bounded JSON-object metadata, and malformed, duplicate, absent, and excessive-part cases. |
| 6 | confirmed — The parser metadata-part bound is now deliberately above the application metadata-size bound, creating separate observable bands. Task 2.1 tests the application boundary directly, task 3.2 tests a value between the bounds, and probe 8.12 removes only the application guard, so every mapped validation check now has an independent one-guard failing-input probe. |

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-21
**Reviewed-Commit:** 7a8b4ea184a77ee27edc5f806a4d2987305a0572
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | blocker | `app/services/assets.py:107-117`; `tests/integration/test_prune.py:200-224` | The upload writes and inspects its staged original before opening the transaction and taking the shared advisory lock. During that unprotected interval, prune can take the exclusive lock and act even though an upload is in flight; once the staged file is older than the grace cutoff (uploads may be delayed without bound), prune can delete it as an orphan and the upload cannot complete. This contradicts the requirement that every upload hold the shared claim for the whole write and that prune change nothing while any upload is in flight, as well as task 7.5's claimed ordering. The concurrency test pauses only after `publish_files`, so it cannot expose the gap. Acquire the shared lock before creating the first staged file (or specify and implement an equivalent protocol covering staging), and add an unbounded-delay test with prune racing the pre-publication stage. | fixed |
| 2 | major | `app/storage.py:85-95`; `app/services/assets.py:61-68,79-82,135-138` | A failed staged write leaves a partial `.part` file behind. `MediaStorage.fill()` does not unlink its target on an iterator/write/flush/fsync failure; if the original fill fails, `stage_upload()` never returns its path so `staged` remains `None`, and if the thumbnail fill fails, its local staging path is likewise unknown to `_clean_up()`. Thus a failed upload can leave a file of that upload on disk, contrary to the whole-asset and thumbnail-failure scenarios. Make staging cleanup exception-safe for both files and add failure-injection tests for the original and thumbnail writes. | fixed |
| 3 | major | `app/api/assets.py:146-156`; `tests/api/test_asset_upload.py:159-173` | The exactly-one-file check counts only `UploadFile` values whose field name is `file`. A request containing one valid `file` part plus a second file part under any other field name is accepted and the extra file is silently ignored, although the spec requires exactly one file part in the entire upload. The current two-file test uses the name `file` for both parts and misses this case. Count all `UploadFile` parts, require the sole one to be named `file`, and cover a differently named extra file. | fixed |
| 4 | major | `app/services/images.py:111-120`; `tests/unit/test_images.py:130-138` | Accepted pictures smaller than 256 px are not resized to the specified thumbnail size: Pillow's `thumbnail()` never enlarges, and the implementation explicitly preserves the smaller dimensions. The specification and FR-AST-6 require the thumbnail's longest side to be 256 px, while accepted originals may be as small as 32 px. Either produce the required size or revise the requirement through the change process; add coverage for an accepted source below 256 px. | fixed |
