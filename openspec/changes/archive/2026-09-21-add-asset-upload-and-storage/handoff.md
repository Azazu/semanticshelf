# Handoff — add-asset-upload-and-storage

**Updated:** 2026-09-21 · claude
**State:** merged
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

Merged into `main` as `31b0439` and archived. The capabilities it introduced
live in `openspec/specs/asset-upload/spec.md` and
`openspec/specs/asset-api/spec.md`; the readiness requirement it changed lives
in `openspec/specs/health-probes/spec.md`.

## Blockers

None.
