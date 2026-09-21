## 1. The walk

- [ ] 1.1 Write `app/services/folder.py` with the walk: from a directory and the recursive flag, yield each entry classified before anything is opened — candidate, or skipped with a reason (not a regular file, a link out of the tree, no picture extension, unreadable). Classification uses `lstat` and `resolve().is_relative_to()`, never `is_file()` (design decisions 2 and 3). Verify: `tests/unit/test_folder_walk.py` builds a fixture tree with a picture, a text file, a file with a lying extension, a symlink inside the tree, a symlink out of it, a symlink to a parent directory, a fifo and a subdirectory, and asserts the exact classification of each, with and without the recursive flag.
- [ ] 1.2 The walk is sorted and terminates on a tree containing a link to its own parent (design decision 10 and 3). Verify: the same unit test asserts the order of what it yields and that the run visits each real file exactly once.
- [ ] 1.3 A directory that does not exist, is not a directory, or cannot be read is refused before anything is walked, naming it. Verify: unit tests for all three, including a directory whose permissions deny reading.

## 2. Importing a file through the pipeline

- [ ] 2.1 Extend `app/services/folder.py` with the per-file import: open the candidate, call `create_asset` with `source = folder`, the file's own name as `original_filename`, the run's tags, and the run's metadata merged under the recorded relative path (design decision 7). Nothing in `app/services/assets.py` changes. Verify: an integration test imports a folder and asserts the stored asset is identical to the same picture uploaded over HTTP, apart from `source`, the filename and the recorded path; `git diff --stat app/services/assets.py` is empty.
- [ ] 2.2 The run's tags and metadata are validated once, before the walk starts, through the same normalisation an upload uses; an unacceptable value refuses the run with nothing stored. Verify: unit tests for a bad tag and for oversized metadata, and an integration test asserting the store is untouched after such a refusal.
- [ ] 2.3 A file whose recorded path would push its metadata past the bound is refused with that reason, and the run continues. Verify: an integration test with a deep enough path.
- [ ] 2.4 Every outcome per file — created, already stored, refused with the reason, skipped with the reason — is recorded in a report object, and the run never stops at the first failure. Verify: an integration test over a mixed fixture tree asserts every count and every reason.

## 3. The dry run

- [ ] 3.1 A dry run walks, hashes, inspects and looks up the hash, and writes nothing: no file under the media root, no asset, no job, no change to an existing asset (design decision 6). Verify: an integration test snapshots the media root and the three tables before and after, and asserts both are unchanged while the report names what would have been created.
- [ ] 3.2 The dry run's verdicts equal the real run's: for the same tree, what it says would be created, refused or already stored is what a real run then does. Verify: an integration test runs both over one fixture tree and compares the reports field by field.

## 4. The command

- [ ] 4.1 Add `index-folder` to `app/cli.py`: the directory argument, `--recursive`, `--tags`, `--meta`, `--dry-run`, `--no-index`; it builds the settings, storage, session factory and inference pool, calls the service and prints the report through a `describe`-style renderer, as `storage prune` does. Verify: `uv run semanticshelf index-folder --help` is pasted into the commit body, and a CLI test asserts the summary's lines for a fixture tree.
- [ ] 4.2 Exit status: 0 when the run completed, even with refusals; non-zero when it could not run at all (design decision 9). Verify: CLI tests asserting both, including the exit code for a missing directory.
- [ ] 4.3 After a successful run the command drains the work it queued through `indexing.drain`, repeatedly and boundedly, unless `--no-index` was given, and reports how much work it carried out (design decision 8). Verify: an integration test asserts vectors exist for every imported asset after the command returns, and that with `--no-index` the work is pending and no vector exists.
- [ ] 4.4 Progress is shown for both phases with `click`'s progress bar, and no new dependency is added. Verify: `uv run semanticshelf index-folder .data/demo` run by hand with its output pasted into the how-to; `uv lock --check` unchanged.

## 5. Failing inputs (high tier: one per new check)

One row per new guard, one probe per row; each removes exactly that guard,
runs the named test, records the output in the commit body and restores the
code.

| New check | Probe |
|---|---|
| Only regular files are opened (`lstat`, not `is_file`) | 5.1 |
| A symlink out of the tree is not read | 5.2 |
| A symlinked directory is not descended into | 5.3 |
| Candidates are chosen by extension | 5.4 |
| The bytes still decide what a file is | 5.5 |
| Tags and metadata are validated before the walk | 5.6 |
| The recorded origin is not overwritten by the run's metadata | 5.7 |
| `original_filename` stays a bare name | 5.8 |
| A dry run writes nothing | 5.9 |
| A refusal does not stop the run | 5.10 |
| A missing directory exits non-zero | 5.11 |
| The drain after the import is bounded | 5.12 |

- [ ] 5.1 Classify with `is_file()` instead of `lstat`: the fifo and the outside symlink tests fail.
- [ ] 5.2 Remove the containment check: the outside-symlink test fails, showing a file from beyond the tree stored.
- [ ] 5.3 Follow directory symlinks in the walk: the parent-link test fails or does not terminate within its timeout.
- [ ] 5.4 Accept every regular file as a candidate: the test that a document is skipped rather than refused fails.
- [ ] 5.5 Trust the extension instead of the bytes: the lying-extension test fails, showing a text file stored as a picture.
- [ ] 5.6 Validate the tags after the walk instead of before: the test that a bad tag leaves the store untouched fails.
- [ ] 5.7 Merge the run's metadata last: the test that the recorded origin survives fails.
- [ ] 5.8 Put the relative path in `original_filename`: the test that the field holds a bare name fails.
- [ ] 5.9 Let the dry run call `create_asset`: the snapshot test fails.
- [ ] 5.10 Re-raise the first refusal: the mixed-tree test fails, showing a run that stopped.
- [ ] 5.11 Exit 0 for a missing directory: that CLI test fails.
- [ ] 5.12 Drain in an unbounded loop: the test that the command returns on a queue holding work it did not create fails.

## 6. Documentation and the requirement amendments

- [ ] 6.1 Extend `docs/how-to/uploading.md` or add a section to `docs/how-to/indexing.md` with the import: the command, its options, the summary, the dry run, and what is skipped and why. Verify: every command run in its exact form, output pasted from the run, the file re-read whole afterwards.
- [ ] 6.2 Add the command to `docs/reference/commands.md`. Verify: the row matches `--help` word for word.
- [ ] 6.3 Amend FR-CLI-1 in `docs/explanation/requirements.md`: the relative path is metadata and `original_filename` keeps its guarantee; `INDEXING_RUNNER` arrives with change 13 and `--no-index` stands in for it until then. Verify: `rg "original_filename" docs/ openspec/` shows no surviving claim that it holds a path.
- [ ] 6.4 The tier correction of row 7 (made when this change was proposed) still holds at the end. Verify: `rg -n 'add-folder-indexing-cli' openspec/ROADMAP.md docs/explanation/requirements.md` shows `high` in both, and `proposal.md` agrees.

## 7. Wrap-up

- [ ] 7.1 Commits per logical block, no agent trailers, each body naming the evidence for the tasks its diff holds. Verify: `git log --format=%B main..HEAD | grep -c '^Co-Authored-By'` prints `0`.
- [ ] 7.2 `env -u DATABASE_URL make check` green and `make test-integration` green against pgvector. Verify: both outputs recorded in a commit body.
- [ ] 7.3 Acceptance on GitHub (the user pushes the branch): both jobs green. Verify: the user reports the run.
- [ ] 7.4 `openspec validate add-folder-indexing-cli --strict` and `scripts/pregate-verify.sh gate2 add-folder-indexing-cli` pass; request Gate 2 with `/gate-review add-folder-indexing-cli 2`.
