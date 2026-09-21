# Import a folder of pictures from the command line

**Risk-Tier:** high

## Why

Every asset in the store today arrived through one HTTP request at a time.
That is fine for a demonstration of the endpoint and useless for filling a
corpus: the demo dataset of change 9, a photo directory an operator already
has, a re-import after a wipe — all of them are folders, and there is no way
to point the service at one.

The work is small because everything it needs exists: change 5 built the
pipeline that turns bytes into a stored asset, change 6 made an asset queue its
own indexing. This change is the walk that feeds them, and the honest summary
of what happened to each file.

It is `high` rather than the `medium` the roadmap projected, and the proposal
raises it deliberately. The command walks a directory tree the operator names,
which is path handling — an explicit `high` trigger in AGENTS.md. Three things
have to be decided before code exists rather than after: what a symbolic link
inside that tree may do, what happens when a "file" is a fifo or a device node
that never ends, and what `--dry-run` is allowed to touch. The roadmap row and
§7 of the requirements are corrected to `high` with this change.

## What Changes

- New command `semanticshelf index-folder <dir>` with `--recursive`,
  `--tags`, `--meta`, `--dry-run`, feeding every candidate file through the
  same path an upload takes: the same inspection from the bytes, the same
  thumbnail, the same storage rules, the same duplicate check by content hash,
  the same work queued per enabled model in the same transaction as the asset.
- The walk is bounded by construction: it never leaves the directory it was
  given (a symbolic link to a directory is not followed, a symbolic link to a
  file outside the tree is not read), it opens only regular files, and it
  considers only files whose extension is one the service accepts — with the
  bytes still deciding, as everywhere else.
- `source = folder` for everything the command stores, which the store's value
  domain already allows.
- `original_filename` holds the file's own name and `meta.source_path` holds
  its path relative to the imported directory. FR-CLI-1 asks for the relative
  path in `original_filename`, but change 5 deliberately reduces that field to
  its last segment so that no path and no `..` survives in it; the requirement
  is amended to keep the guard and put the path where a path is text.
- `--dry-run` reads and inspects but writes nothing at all: no file under the
  media root, no row, no job. It reports exactly what a real run would do,
  including which files are already stored.
- A summary at the end, and a non-zero exit only when the run could not be
  performed: how many were created, how many were already stored, how many
  were refused with the reason, how many were skipped and why.
- After a successful run the command drains the queue it filled, through the
  same `drain` an upload schedules, so a folder import ends with vectors
  rather than with a backlog nothing will pick up until the next upload.
  `--no-index` leaves the work queued instead. `INDEXING_RUNNER`, which
  FR-CLI-1 names, belongs to the worker of change 13 — until that process
  exists there is nothing for the setting to select, so the flag stands in its
  place and the requirement is amended to say so.

## Non-goals

- The `worker` process and `INDEXING_RUNNER` (change 13), and the demo dataset
  that will call this command (change 9).
- Any search endpoint, and any change to how a picture is inspected, stored or
  queued: this change adds no rule to the pipeline, it only feeds it.
- Watching a folder, incremental re-import by modification time, or any state
  remembered between runs. A second run over the same folder is a run in which
  every file is a duplicate, which is exactly what the summary should say.
- Parallel import. The pipeline holds a shared lock over the media root per
  asset; a folder import is a background operation and does not need to race
  itself.
- Moving, renaming or deleting anything in the imported directory. The command
  reads it and nothing else.

## Capabilities

### New Capabilities

- `folder-indexing`: importing a directory of pictures — which files are
  considered, what the walk may not do, what is stored for each one, what a
  dry run promises, and what the summary reports.

### Modified Capabilities

- `asset-upload`: the pipeline's requirements gain the second entrance. What
  an asset is and how it is stored does not change; what changes is that the
  rules are stated for both callers, and that an import records where the file
  came from.

## Impact

- New: `app/services/folder.py` (the walk and the per-file outcome),
  `index-folder` in `app/cli.py`, a how-to section, tests over a fixture tree.
- Changed: `docs/reference/commands.md`, `openspec/ROADMAP.md` and §7 of
  `docs/explanation/requirements.md` (the tier), FR-CLI-1 (the two amendments
  above).
- Unchanged: the schema, the API, the upload service and the storage module.
  If this change needs to modify `app/services/assets.py` beyond passing a
  source and metadata, that is a signal the pipeline was not reusable and the
  design has to say why.
- No new dependency: `typer` is already the CLI, and its progress bar comes
  from `click`, which typer already requires.
