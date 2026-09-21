# Design — add-folder-indexing-cli

## Context

See `proposal.md` — Why. The pipeline this command feeds already exists:
`app/services/assets.py::create_asset` takes an open file, inspects it, writes
both files, the row and the work in one transaction, and raises
`DuplicateAssetError` when those bytes are already stored; `app/services/
indexing.py` claims, executes and finishes that work. What does not exist is
anything that turns a directory into a sequence of calls to them, and that is
the whole of this change.

Two constraints shape the design. The directory comes from the operator, so
the walk is the only part of the service that reads paths it did not generate —
and a path is not a thing, it is a name that can mean something else a
microsecond later. And the stated non-goal is that the storage pipeline stays
untouched: if this change finds itself editing `create_asset`, the design was
wrong.

Measured on this machine, Python 3.12.14, so that the decisions below rest on
behaviour rather than on belief:

| Probe | Result |
|---|---|
| `os.fwalk(root)` over a tree holding a symlinked directory and a symlink to its own parent | both are listed as directories, neither is entered, and the walk terminates; each call yields a descriptor for the directory it is in |
| `os.open(name, O_RDONLY\|O_NOFOLLOW\|O_NONBLOCK\|O_CLOEXEC, dir_fd=…)` on a symlink to a file outside the tree | refused by the kernel with `ELOOP` — the name is never resolved through the link |
| the same open on a fifo named `pipe.png` | succeeds immediately instead of blocking (that is what `O_NONBLOCK` buys), and `os.fstat` on the descriptor reports a fifo, not a regular file |
| the same open on a regular file | succeeds, `os.fstat` reports a regular file and its size, and `open(fd, "rb")` reads the bytes of **that** descriptor |
| `Path.is_file()` on a symlink to a file | `True` — it follows the link, which is why no decision below uses it |

## Goals / Non-Goals

**Goals.** A walk whose refusals are decided on the object that is actually
read, not on a name that was true a moment ago; one import path shared by the
real run and the dry run, so their verdicts cannot drift; a summary that
accounts for every file the walk considered and for every asset whose work it
could not finish.

**Non-Goals (design level).** No parallelism, no resumable state file, no
progress reporting beyond the two phases (import, then indexing), and no new
settings: the run is described entirely by its arguments.

## Decisions

1. **The walk and the import live in `app/services/folder.py`; the CLI only
   prints.** The command is a thin `typer` shell over a function that takes the
   directory, the options and a session factory, and returns a report — the
   same shape `storage prune` already has (`prune` returns a report, `describe`
   renders it). This is what makes the whole thing testable without a terminal,
   and what keeps the summary's wording out of the logic.
   Rejected: putting the walk in `app/cli.py`, which would make every test a
   CLI-runner test and every assertion a string match.

2. **What is validated is the descriptor, not the path.** The walk is
   `os.fwalk`, which hands out a descriptor for the directory it is currently
   in; each candidate is opened relative to that descriptor with
   `O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`, and the open's own result
   decides:

   - a symbolic link is refused by the kernel (`ELOOP`) — the link is never
     resolved, so nothing outside the tree can be reached through one;
   - a fifo, socket or device node opens without blocking and is then rejected
     because `os.fstat` on the descriptor does not report a regular file;
   - a regular file is read through that descriptor and nothing else.

   This is the answer to the race the previous draft left open: a name checked
   and then opened can be swapped in between, but a descriptor cannot. The
   file that is hashed, inspected and stored is the object the open returned.
   Resolving names against a directory descriptor extends the same property to
   the directory chain: replacing a parent directory with a symlink mid-walk
   does not redirect an open, because the descriptor still refers to the
   directory the walk entered.
   What this does NOT guarantee: the *contents* of a file can still change
   while it is being read — the hash and the stored bytes are the bytes that
   were read, which is the same guarantee an upload gives. And nothing here
   defends against a directory the operator names deliberately:
   `index-folder /dev` simply finds no regular picture.

3. **Containment is structural, and no symbolic link is read at all.** There
   is no separate "is this path inside the tree" check, because there is
   nothing left for it to catch: `os.fwalk` does not enter a symlinked
   directory (measured), and `O_NOFOLLOW` refuses a symlinked file. A link
   inside the tree pointing inside the tree is refused too — the previous
   draft allowed it, which contradicted the rule that only a regular file is
   opened, and the reviewer was right that both could not hold. One rule:
   **regular files only, symlinks are skipped and reported.**
   The named directory is **opened** exactly once, before the walk, and every
   step afterwards — the count, the walk, the report's own `directory` — works
   from that descriptor. A run may be pointed at a symlink to a directory and
   behaves as if it had been pointed at the directory; if what the name leads
   to is not a directory, the run is refused before anything is read.
   Resolving is not enough on its own, and two rounds of review proved it. The
   first implementation resolved in three places — once for the report, once
   inside the walk, once for the progress bar's count — so the name could be
   replaced between them and the run could end up in a tree the report did not
   name. The second still resolved the name and *then* opened the resolved
   path, which is two steps with a window between them: the open could land on
   a replacement while the report kept the original name, leaving a run reading
   one tree and naming another.
   So there is no resolution step at all now. `open_root` opens the name it was
   given — following a symbolic link to a directory, which is allowed — and
   then asks the kernel what that descriptor refers to (`/proc/self/fd/<n>`),
   which is what the report names. One syscall decides both, so the two cannot
   disagree, and the same rule as for a file holds for the root: what is worked
   on is the object that was opened, not the name it had.
   Where `/proc` is missing the name is resolved and then *proved* to be this
   directory — the descriptor's device and inode against the resolved path's —
   and a name that no longer leads to the directory being held ends the run
   instead of being reported as its label. The requirement is unconditional, so
   the fallback has to be too: a name that cannot be proved is not printed.
   That is the third shape this decision has had; the two before it are written
   above because each was refused for a reason worth keeping.

4. **Candidates are chosen by extension, accepted by bytes.** The walk
   considers a file whose suffix is one the service stores (`FILE_EXTENSIONS`,
   case-insensitive) — plus `.jpeg`, which is the same format under its other
   spelling and is what half a photo folder is called — and counts everything
   else as skipped; what a candidate *is* is still decided by decoding it, so a
   text file called `photo.png` is refused exactly as an upload of those bytes
   would be.
   Rejected: inspecting every regular file. On a folder that is not a photo
   folder it turns every document into a "refused" line, which buries the
   refusals that matter; and the operator who really wants that can point the
   command at a narrower directory.

5. **Each file is its own transaction, and a run is not atomic.** `create_asset`
   is called once per file; a run interrupted halfway leaves exactly the assets
   it had already created, each whole. That is deliberate: the alternative —
   one transaction for the folder — holds the media lock for the length of the
   import and loses everything on the last file's failure. Re-running the same
   folder is the recovery, and it is safe because every file already stored is
   a duplicate. Idempotent by the content hash, not by bookkeeping.

6. **The dry run and the real run share every decision up to the write.** Both
   walk the same way, open the same way, hash the same way, inspect through the
   same `images.inspect`, and look the hash up the same way; they differ only in
   what happens next — `create_asset`, or nothing.
   One thing the rehearsal has to do for itself: remember the hashes it has
   already called new. The store cannot tell it, because a dry run writes
   nothing to the store, so without that memory two files of identical bytes in
   one folder are both reported as new while a real run stores the first and
   counts the second as already there. The rehearsal therefore carries the set
   of hashes it has seen, and consults it as well as the store.
   What this does NOT guarantee: a dry run is not a lock. A file it reports as
   new can be stored by an upload a second later.

7. **The file's own name is the original filename; its relative path is
   metadata.** `normalise_filename` reduces a value to its last segment so that
   no path survives in that field (change 5), and this change does not weaken
   it. The relative path is recorded under a reserved metadata key, through the
   same metadata checks as any other value — so a file whose recorded path
   pushes the run's metadata over its bound is refused with that reason, like
   any other oversized metadata. (A path long enough to break the bound by
   itself does not exist: a filesystem stops at four kilobytes and the bound is
   eight. The check is per file because the path is per file, not because a
   path can be enormous.) The run's own `--meta` is merged first and the recorded
   origin last, so a run cannot overwrite it by accident.
   FR-CLI-1 asks for the relative path in `original_filename`; the proposal
   amends it, because the field's guarantee is older and stronger than the
   sentence that would break it.

8. **The import carries out its own work, and says what it could not
   finish.** The previous draft called `drain` a bounded number of times, which
   cannot deliver what it promised: `drain` claims whatever is due in the whole
   queue, so a queue holding older work would swallow every pass while this
   run's jobs stayed pending. Two changes make the guarantee real:

   - `app/repositories/jobs.py::claim` and `app/services/indexing.py::run_batch`
     gain an optional set of asset identifiers. With it, a claim takes only
     work for those assets — the same query with one more predicate. Without
     it, every existing caller behaves exactly as before.
   - the command loops over its own assets: read the state of their work
     (`latest_status_for`, one query), stop when none is `pending` or
     `running`, otherwise claim and execute another targeted batch. A pass that
     claims nothing while work is still unfinished means the work is not
     claimable now — another runner holds it, or it is waiting out its backoff
     — and the loop stops rather than spinning.

   The loop is bounded twice over: by that "a pass that took nothing ends it"
   rule, and by a pass count derived from the number of jobs and the configured
   attempts. What the command guarantees is therefore precise: **when it
   returns, every asset it created has either a vector or a job the queue still
   owns**, and the summary says which — indexed, still queued with the reason it
   was not carried out, or failed with the reason the queue recorded. A job that
   fails does not fail the import; it is reported.

   **The import does not wait out a backoff.** This is the consequence the first
   draft of this decision hid, and the reviewer was right to refuse it: a job
   that fails an attempt while attempts remain becomes due again only after
   `2^attempts × 10s`, so the very next targeted claim takes nothing and the run
   ends with that job queued. Waiting for it would mean sleeping in a CLI for a
   delay that doubles — a scheduler, which is a non-goal — and it would make
   every test of the path a slow one. So a retriable failure is reported as
   still queued, a terminal one (the attempts are spent) is reported as failed,
   and the two are never conflated. The operator's answer to "still queued" is
   the same as everywhere else in this service: run the queue again.

   `INDEXING_RUNNER` (FR-CLI-1) selects between this runner and the worker
   process; until change 13 there is no second runner to select, so `--no-index`
   stands in its place.

9. **Exit status: 0 when the run completed, non-zero when it could not run.**
   A refused file is a result, not an error — it is in the summary with its
   reason. A directory that does not exist, is not a directory after
   resolution, or cannot be read is an error before anything is read, and so
   are tags or metadata the service would refuse: those are checked once,
   before the walk starts, so a run cannot store half a folder under a tag it
   then rejects.

10. **The walk is sorted.** Directory order is filesystem order, which is not
    stable between machines; sorting makes the summary reproducible and the
    tests deterministic, and costs nothing at the scale a folder import runs at.

## Applicability

| Question | Answer |
|---|---|
| Crash before/after an external effect | Files are written before the row, as at upload; a crash between them leaves files with no asset, which is the residue `storage prune` exists to find. A crash mid-run leaves the assets already created, whole — decision 5. |
| Concurrent writers | Two imports of the same bytes, or an import racing an upload, are decided by the unique content hash and the shared media lock `create_asset` already takes. The import's own runner competes for jobs with any other runner through the same claim and lease — a job another runner holds is not claimed twice, and the loop of decision 8 stops rather than waiting for it. |
| A tree that changes under the walk | An entry replaced between being listed and being opened cannot change what is read: the open is by descriptor with `O_NOFOLLOW`, and the descriptor is what is validated and read (decision 2). A file that disappears in between is reported as skipped. Task 1.4 forces exactly this interleaving. |
| Empty / zero / null inputs | Defined and each with its own task: an empty directory and a directory with no candidates both succeed with a summary of zeros (task 1.5); a zero-byte file is a candidate by its extension and is refused as undecodable, as an upload of zero bytes is (task 2.5); a named directory that is a symlink is resolved once and walked as its target (task 1.6); a run with neither tags nor metadata records only the origin (task 2.1). |
| Idempotency of retries | Re-running the same folder creates nothing and reports every file as already stored — decision 5. Re-running after an interruption is the documented recovery. |
| Deletion / expiry | n/a — the import never deletes or expires anything, in the store or in the imported directory. |
| Authorization boundary | n/a — the command runs with the operator's own privileges on their own machine; there is no caller to authorize. |
| Money rounding | n/a. |

## Risks / Trade-offs

- **A very large folder** → memory stays flat (one file at a time, hashed in
  chunks by `receive`), but the run is serial and can take a long time. The
  summary is printed at the end; the progress bar is what tells the operator it
  is alive. No pagination, no resume, by the non-goals.
- **The copy `receive` makes** → every imported file is copied to a temporary
  file outside the media root before it is stored, which doubles the write.
  Accepted deliberately: the alternative is a second path into storage that
  bypasses the staging rule change 5 built, and that rule is why prune is safe.
- **A targeted claim is not fair** → while the import finishes its own work it
  can take jobs ahead of older ones it did not create. Accepted: it is an
  operator command finishing what it started, it holds no lease longer than any
  other runner, and the queue's order is otherwise untouched.
- **Work the import cannot finish** → a job waiting out its backoff, or one
  another runner holds, leaves the command reporting "still queued" with that
  reason rather than waiting. An import of a folder whose pictures fail on the
  first attempt therefore ends with nothing indexed and everything queued,
  which the summary states plainly. The operator's answer is to run the queue
  again — which is what the runner inside the API, and the worker of change 13,
  do anyway.
- **The dry run's verdicts can age** → decision 6; the summary says it was a
  dry run so nobody reads it as a receipt.
- **`run_batch` in a CLI process loads a model** → the first imported picture
  pays for the model load, in this process, on the inference pool. With
  `--no-index` or `MODEL_WARMUP` it is paid elsewhere.

## Migration Plan

None. The command is new, the claim's new argument is optional and every
existing caller keeps its behaviour, and no migration is written: `source =
'folder'` is already in the store's value domain (change 3) and `meta` is
schemaless JSONB.

## Open Questions

None. The questions Gate 1 raised — what binds validation to the object that is
read, whether an in-tree symlink may be read, what the import may promise about
vectors, and what happens to an empty directory or a symlinked root — are
decided above (2, 3, 8) and in the Applicability table, and each has a task.
