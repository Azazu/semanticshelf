# Design — add-asset-upload-and-storage

## Context

See `proposal.md` — Why. What exists: the `assets` table with its domains and
its unique content hash (change 3), repositories that return domain objects,
problem details for every error, request-id logging, and Pillow as a
dependency (change 4). What does not exist: any router beyond the probes, any
request or response schema, any file the service owns.

Constraints that shape the approach: `make check` must stay green without a
database and without weights, so the upload path has to be testable with a
temporary directory and no container; the event loop must not block, and file
I/O and image decoding are both blocking; and every path touching the
filesystem is security-sensitive input handling, which is why this change is
`high` tier.

## Goals / Non-Goals

**Goals:** a picture can be uploaded, read, listed, edited and deleted; the
bytes on disk are reachable only through an identifier the service generated;
a crash leaves at most removable orphan files; every limit is enforced before
the work it bounds.

**Non-Goals:** see `proposal.md` — Non-goals. At design level: no abstraction
over the filesystem (no pluggable object store — the requirements name a
directory, and an interface with one implementation is a guess about the
future), and no background work of any kind.

## Applicability

| Question | Applies | How it is handled |
|---|---|---|
| Crash before/after an external effect | yes | The external effects are two file writes and one row. Order: both files renamed into place, then the row; a failed insert unlinks both. A crash between them leaves orphan files — the one residue the design permits — which `storage prune` finds. The reverse order (row first) is rejected: it would let a row point at a file that never arrived. |
| Concurrent writers | yes | Two races, not one. **Upload against upload:** two identical uploads race on the unique content hash; both may pass the pre-check and write files under their own identifiers, and the insert that loses raises a unique violation, is translated to 409 and unlinks its own files — neither can touch the other's, because every path derives from its own identifier. **Prune against upload:** between the renames and the commit, an upload's files look exactly like orphans. Prune therefore only considers files older than a grace period (decision 12), and an integration test holds an upload at that exact point while prune runs. |
| Money rounding | n/a | No money anywhere in the project. |
| Empty/zero/null inputs | yes | An empty file part decodes as nothing → 415. Zero tags and absent metadata are normal. `meta: null` in a patch means "clear", an omitted field means "leave alone", distinguished through the fields actually present in the request rather than through the value. A zero-byte upload never reaches decoding, because the byte limit check reads and hashes what arrived. |
| Authorization boundary | yes | There is none by design (single-tenant, unauthenticated), so the boundary that matters is the path: nothing a client sends may reach the filesystem. One module builds paths, from an identifier the service generated and a format it detected; the original filename is stored as text and never used to open anything. |
| Deletion/expiry | yes | Deletion removes the row and everything derived from it in one transaction, then the files. A failed unlink is a warning, not a failed request, because the row is already gone and retrying the whole delete would answer 404. Prune reconciles. A second delete answers 404 deliberately. |
| Idempotency of retries | yes | Upload is not idempotent and does not pretend to be: a retry of the same bytes answers 409 naming the existing asset, which is the honest answer and lets a client converge. Delete is not idempotent at the HTTP level either, by requirement. |

## Decisions

1. **One module builds paths: `app/storage.py`.** It takes an asset
   identifier and a format and returns a path under the resolved media root;
   it writes, removes and walks. Nothing else in the application joins a path
   under that root, and a unit test asserts every derived path stays inside
   the resolved root for adversarial identifiers and extensions.
   Rejected: building paths inside the service layer, which is where this kind
   of defect usually hides — a filename that reaches `Path()` once is enough.

2. **Two bounds, both enforced by something that sees the stream.** Verified
   against the installed stack rather than assumed: FastAPI 0.141 parses the
   whole multipart body before the endpoint runs (`await request.form()` in
   its routing layer), so counting chunks inside the endpoint cannot bound
   anything — by then the body has already been read and spooled. Worse, that
   call uses Starlette's defaults, and `max_part_size` defaults to 1 MiB, so a
   plain `UploadFile` parameter would reject an ordinary 5 MiB photograph with
   a parser error.

   Therefore:
   - **The whole body** is bounded by a small ASGI middleware that counts the
     bytes of the request stream as they arrive and refuses at the configured
     limit with 413 problem details. It works on a chunked request with no
     `Content-Length`, because it counts what actually arrives rather than
     trusting a header, and it covers every part and all multipart overhead,
     which is what NFR-SEC-5 requires.
   - **The file part** is bounded by the parser itself: the endpoint calls
     `request.form(max_part_size=<the upload limit>, max_files=…,
     max_fields=…)` explicitly instead of taking an `UploadFile` parameter,
     and a `MultiPartException` becomes 413 problem details rather than the
     parser's own 400.

   The content hash is then computed by reading the part in chunks, which is
   about not holding the file in memory, not about the limit.
   Rejected: trusting `Content-Length` (absent or false on a chunked request);
   relying on a reverse proxy (there is none in development, and the service
   must be safe on its own); and leaving the parser at its defaults, which
   would silently cap uploads at 1 MiB.

3. **The pixel cap is our own check on the header, with the library's guard
   behind it.** Read from the installed Pillow 12.3 rather than assumed: its
   `_decompression_bomb_check` only *warns* above `MAX_IMAGE_PIXELS` and
   raises above **twice** that value, so configuring it to the cap would let a
   picture of `cap + 1` pixels through — and FR-AST-3 requires a refusal above
   the cap exactly.

   The upload therefore opens the file (which reads the header and allocates
   no pixels), multiplies its declared dimensions, and refuses above the cap
   with 422 before anything is decoded. Pillow's own guard stays configured at
   the cap as a second line for code paths that do not go through this check,
   and the boundary is evidence: a picture at exactly the cap is accepted, one
   at the cap plus one pixel is refused.
   Rejected: relying on the library's guard alone (it does not enforce the
   number the requirement names); promoting its warning to an error with a
   warnings filter (a process-global that any dependency can reset, and it
   still fires only on the header path Pillow chooses to check).

4. **Two files, one unit.** Each file is written to a temporary name in its
   target directory, flushed, and renamed into place — a rename within a
   directory is atomic, so no half-written file is ever visible under the name
   the service serves. The row is inserted after both renames; any failure
   from there unlinks both. Shard directories are created on demand; the media
   root itself is never created by the service, so a mistyped root is reported
   by readiness instead of being silently created next to the real one.

5. **The thumbnail is re-encoded from decoded pixels.** That is what strips
   every metadata block of the original — camera data, colour profile,
   comments, and anything hidden in one — rather than an explicit strip list
   that a new block type would slip past. Size and quality are constants of
   the storage module, not settings: the requirements fix them, and a knob
   that no deployment turns is a knob that rots.

6. **Blocking work runs off the event loop.** Image decoding, thumbnailing and
   file writes go through the threadpool, not the event loop. This is
   Starlette's shared threadpool rather than the inference pool of change 4:
   that pool is sized for model work and a burst of uploads must not stall
   embedding.

7. **Serving bytes is a file response with validators.** The framework's file
   response streams from disk; the entity tag is the content hash, which the
   service already stores, so revalidation costs no read. Existence is checked
   before the response is built, so a missing file is a 404 with a warning
   rather than an exception mid-stream.

8. **`has_more` by fetching one extra row**, as the requirements state, rather
   than a count query: the count would be a second query whose answer is stale
   the moment it is read, and the API deliberately exposes no total.

9. **Patch distinguishes absent from null through the request's own fields**,
   not through a sentinel value in the schema, so the two cases the
   requirement separates stay separate all the way to the repository.

10. **The media readiness check does not touch the database and runs beside
    it.** It asks the operating system whether the root exists, is a directory
    and is writable, in a thread and under the same budget as the other
    checks, so the probe's bound of about twice the timeout still holds. It
    does not write a probe file: readiness is polled continuously, and writing
    on every poll is a side effect a health check should not have. It
    therefore cannot catch a mount that reports writable and then refuses the
    write — that failure surfaces at the first upload, loudly, and the check's
    description says so rather than claiming more.

12. **Prune ignores files younger than a grace period.** Between its renames
    and its commit, an upload's two files are indistinguishable from orphans:
    final names, no row. A prune running at that moment would delete them and
    leave the invariant this design promises — no row without its files —
    broken by the very command meant to repair it. Prune therefore only
    considers a file whose last modification is older than
    `PRUNE_MIN_AGE_SECONDS` (default one hour, far beyond any upload), and the
    report says how many files it skipped as too young, so nothing disappears
    silently from its view.
    Rejected: a lock shared by every upload and the prune run (a global
    serialisation point for an operation that should never touch a live
    upload); writing files under a temporary prefix and renaming them only
    after the commit (it moves the window rather than closing it, and it means
    a row can exist before its files, which is the state the whole design
    forbids).

13. **The original filename is metadata and is normalised as text.** It is
    never a path component (decision 1), but it is still attacker-controlled
    text that goes into the store and into responses: it is
    Unicode-normalised, stripped of control characters and of both path
    separators, reduced to its last segment, trimmed to the column's bound,
    and dropped entirely when nothing usable remains. One function owns this,
    beside the tag normalisation, and its tests carry the adversarial cases.

14. **The multipart contract is explicit.** Exactly one `file` part is
    required; `tags` may arrive as repeated fields or as one comma-separated
    field, and both forms produce the same normalised set; `meta` arrives as a
    string holding a JSON object and its length is checked before it is
    parsed, so an oversized value is refused without building the object.
    Every deviation — no file part, several file parts, a `meta` that is not
    an object — answers 422 naming what was wrong.

11. **The probe's reason never quotes the path.** A readiness body is
    unauthenticated; the media root is deployment information. The reason says
    what is wrong (missing, not a directory, not writable), not where.

## Risks / Trade-offs

- [A client uploads at the limit repeatedly] → each upload costs the limit in
  I/O before it is refused; there is no authentication to rate-limit against,
  which the requirements accept for a single-tenant service. The limit keeps
  the cost bounded and constant.
- [Pillow's bomb guard is a process-global] → set once from the setting at
  application start; a unit test asserts it, and a probe demonstrates that
  removing the line lets an oversized picture through.
- [Orphan files after a crash] → the only residue the design permits, found
  and removed by `storage prune`; the alternative (a row before its files)
  trades a removable file for a broken asset.
- [Prune deleting the files of an upload in flight] → the grace period of
  decision 12, with an integration test that holds an upload between its
  renames and its commit while prune runs with the apply flag.
- [The body-size middleware sees every request, not just uploads] → it counts
  bytes and compares an integer; the cost is a few instructions per chunk, and
  applying it to everything means no future endpoint can forget it.
- [`os.access` is an approximation of "writable"] → decision 10; the first
  upload is the real test, and it fails loudly.
- [Deleting the row before the files can strand files] → deliberate: the
  request succeeds, the warning is logged, prune reconciles. The reverse order
  would risk deleting the files of an asset whose row survives.

## Migration Plan

No schema change: change 3 created the table this change fills. Deployment
needs the media root to exist and be writable — `make init` creates the
default, the documentation says so, and readiness reports it when it is
missing. Rollback is removing the router: the stored files become orphans that
`storage prune` lists.
