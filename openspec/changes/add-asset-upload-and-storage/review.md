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
