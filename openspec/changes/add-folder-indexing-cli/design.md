# Design — add-folder-indexing-cli

## Context

See `proposal.md` — Why. The pipeline this command feeds already exists:
`app/services/assets.py::create_asset` takes an open file, inspects it, writes
both files, the row and the work in one transaction, and raises
`DuplicateAssetError` when those bytes are already stored; `app/services/
indexing.py::drain` carries out the work that was queued. What does not exist
is anything that turns a directory into a sequence of calls to it, and that is
the whole of this change.

Two constraints shape the design. The directory comes from the operator, so
the walk is the only part of the service that reads paths it did not generate.
And the stated non-goal is that the pipeline stays untouched: if this change
finds itself editing `create_asset`, the design was wrong.

Measured on this machine, Python 3.12.14, so that the decisions below rest on
behaviour rather than on belief:

| Probe | Result |
|---|---|
| `Path.rglob("*")` over a tree holding a symlinked directory and a symlink to its own parent | both appear as entries; neither is descended into, and the walk terminates |
| `os.walk` with its default `followlinks=False` | same: symlinked directories are listed, never entered |
| A symlink to a file outside the tree | `is_file()` is `True` (it follows the link), `stat.S_ISREG(lstat().st_mode)` is `False` |
| A fifo named `pipe.png` | `is_file()` is `False`; opening it would block forever |
| `link.resolve().is_relative_to(root.resolve())` for that outside link | `False` |

## Goals / Non-Goals

**Goals.** One walk whose refusals are decided before anything is opened; one
import path shared by the real run and the dry run, so their verdicts cannot
drift; a summary that accounts for every file the walk considered.

**Non-Goals (design level).** No parallelism, no resumable state file, no
progress reporting beyond the two phases (import, then indexing), and no new
settings: the run is described entirely by its arguments.

## Decisions

1. **The walk and the import live in `app/services/folder.py`; the CLI only
   prints.** The command is a thin `typer` shell over a function that takes the
   directory, the options and a session factory, and returns a report — the
   same shape `storage prune` already has (`prune` returns a report, `describe`
   renders it). This is what makes the whole thing testable without a
   terminal, and what keeps the summary's wording out of the logic.
   Rejected: putting the walk in `app/cli.py`, which would make every test a
   CLI-runner test and every assertion a string match.

2. **A file is a candidate only if `lstat` says it is a regular file.** Not
   `is_file()`, which follows a symlink and would report a link to anything as
   a file, and not a `try: open()`, which on a fifo blocks forever with no
   timeout to lean on. The classification therefore happens before any open,
   from the entry itself.
   What this does NOT guarantee: nothing here defends against a path the
   operator points at deliberately — `index-folder /dev` will simply find no
   regular picture. The guard is against a tree that contains something
   unexpected, not against an operator importing their own machine.

3. **Containment is by resolution, not by string.** A candidate is read only
   when `path.resolve().is_relative_to(directory.resolve())` — the same shape
   `MediaStorage._checked` uses for the media root, and the only check that
   survives `..` segments, links and case folding on a case-insensitive
   filesystem. A symlink inside the tree pointing inside the tree is read; one
   pointing out of it is skipped and reported.
   The walk itself does not descend into a symlinked directory. Python's
   `rglob` already refuses to (measured above), but that is a library
   behaviour this design depends on, so a test asserts it rather than trusting
   it: a tree with a link to its own parent must terminate and visit each real
   file once.

4. **Candidates are chosen by extension, accepted by bytes.** The walk
   considers a file whose suffix is one the service stores (`FILE_EXTENSIONS`,
   case-insensitive) and counts everything else as skipped; what a candidate
   *is* is still decided by decoding it, so a text file called `photo.png` is
   refused exactly as an upload of those bytes would be.
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
   walk the same way, hash the same way, inspect through the same
   `images.inspect`, and look the hash up the same way; they differ only in
   what happens next — `create_asset`, or nothing. A dry run therefore reports
   the refusals a real run would give, and the one thing it cannot promise is
   that the store has not changed between the two runs.
   What this does NOT guarantee: a dry run is not a lock. A file it reports as
   new can be stored by an upload a second later.

7. **The file's own name is the original filename; its relative path is
   metadata.** `normalise_filename` reduces a value to its last segment so that
   no path survives in that field (change 5), and this change does not weaken
   it. The relative path is recorded under a reserved metadata key, through the
   same metadata checks as any other value — so a tree deep enough to push the
   metadata over its bound refuses that file with that reason, like any other
   oversized metadata. The run's own `--meta` is merged first and the recorded
   origin last, so a run cannot overwrite it by accident.
   FR-CLI-1 asks for the relative path in `original_filename`; the proposal
   amends it, because the field's guarantee is older and stronger than the
   sentence that would break it.

8. **The import drains the queue it filled, through `indexing.drain`.** The
   same function an upload schedules, with a session factory and the inference
   pool the command creates for the run; `--no-index` skips it. A drain takes
   at most `WORKER_BATCH_SIZE` jobs, so the command calls it until the queue it
   filled is empty or a pass does no work — bounded by the number of assets it
   created rather than by a loop that could run forever.
   What this does NOT guarantee: the command does not wait for work that was
   already in the queue before it started, and a job that fails stays in the
   queue under the queue's own rules rather than failing the import.
   `INDEXING_RUNNER` (FR-CLI-1) selects between this and the worker process;
   until change 13 there is no second runner to select, so the flag stands in
   its place.

9. **Exit status: 0 when the run completed, non-zero when it could not run.**
   A refused file is a result, not an error — it is in the summary with its
   reason. A directory that does not exist, is not a directory, or cannot be
   read is an error before anything is read, and so are tags or metadata the
   service would refuse: those are checked once, before the walk starts, so a
   run cannot store half a folder under a tag it then rejects.

10. **The walk is sorted.** Directory order is filesystem order, which is not
    stable between machines; sorting makes the summary reproducible and the
    tests deterministic, and costs nothing at the scale a folder import runs at.

## Applicability

| Question | Answer |
|---|---|
| Crash before/after an external effect | Files are written before the row, as at upload; a crash between them leaves files with no asset, which is the residue `storage prune` exists to find. A crash mid-run leaves the assets already created, whole — see decision 5. |
| Concurrent writers | Two imports of the same bytes, or an import racing an upload, are decided by the unique content hash and the shared media lock `create_asset` already takes; the loser counts a duplicate. Nothing in this change adds a writer of its own. |
| Empty / zero / null inputs | An empty directory, a directory with no candidate files, a zero-byte file, a file whose metadata would exceed the bound, and a directory that is itself a symlink all have a defined outcome, and each has a test. |
| Idempotency of retries | Re-running the same folder creates nothing and reports every file as already stored — decision 5. |
| Deletion / expiry | n/a — the import never deletes or expires anything, in the store or in the imported directory. |
| Authorization boundary | n/a — the command runs with the operator's own privileges on their own machine; there is no caller to authorize. |
| Money rounding | n/a. |

## Risks / Trade-offs

- **A tree whose links or entries change during the walk** → the walk
  classifies each entry when it reaches it; a file that disappears between
  classification and open is reported as skipped with that reason rather than
  crashing the run.
- **A very large folder** → memory stays flat (one file at a time, hashed in
  chunks by `receive`), but the run is serial and can take a long time. The
  summary is printed at the end; the progress bar is what tells the operator it
  is alive. No pagination, no resume, by the non-goals.
- **The copy `receive` makes** → every imported file is copied to a temporary
  file outside the media root before it is stored, which doubles the write.
  Accepted deliberately: the alternative is a second path into storage that
  bypasses the staging rule change 5 built, and that rule is why prune is safe.
- **The dry run's verdicts can age** → stated in decision 6; the summary says
  it was a dry run so nobody reads it as a receipt.
- **`drain` in a CLI process loads a model** → the first imported picture pays
  for the model load, in this process, on the inference pool. With `--no-index`
  or `MODEL_WARMUP` it is paid elsewhere.

## Migration Plan

None. The command is new, nothing that exists changes behaviour, and no
migration is written: `source = 'folder'` is already in the store's value
domain (change 3) and `meta` is schemaless JSONB.

## Open Questions

None. The two the proposal raised — where the relative path is stored, and
what stands in for `INDEXING_RUNNER` before the worker exists — are decided
above (7 and 8) and amended in the requirements by this change.
