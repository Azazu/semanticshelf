# Handoff — add-asset-upload-and-storage

**Updated:** 2026-09-21 · claude
**State:** implementing
**Branch:** change/add-asset-upload-and-storage

## Done this session

Gate 1 passed after one round and four confirmations; everything the change
promises is implemented and tested.

- `app/storage.py` — the only module that builds a path under the media root,
  with staging and atomic publication.
- `app/core/body_limit.py` — the whole-body bound, counted on the ASGI stream,
  which is the only bound on an uploaded file's size on this stack.
- `app/services/{images,tagging,assets,prune}.py` — what a file is, what a
  client may say about it, the upload and its write order under the shared
  media lock, and the reconciliation that never runs beside a live upload.
- `app/api/assets.py` — upload, read, bytes, thumbnail, listing, patch, delete.
- Readiness gained the media check, running beside the database rather than
  after it.
- `semanticshelf storage prune [--apply]`.
- 27 guards, 27 probes, all demonstrated; `docs/how-to/uploading.md` written
  against a running service.

Evidence: `env -u DATABASE_URL make check` 207 passed; `make test-integration`
66 passed; `openspec validate --all --strict` 7 passed; both script suites and
`sh -n` over every script clean; no agent trailer on the branch.

## Next step

The user pushes `change/add-asset-upload-and-storage` and reports the CI run
(task 10.3). On green: tick 10.3 and 10.4 and run
`/gate-review add-asset-upload-and-storage 2`.

## Blockers

None.
