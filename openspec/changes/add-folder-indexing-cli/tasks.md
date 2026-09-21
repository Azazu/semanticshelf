## 1. The walk

- [x] 1.1 Write `app/services/folder.py` with the walk: `os.fwalk` from the resolved directory, each candidate opened relative to that directory's descriptor with `O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`, and what the file is decided by `os.fstat` on the descriptor — never by `is_file()` or by a prior `lstat` on the path (design decisions 2 and 3). Every entry it does not read is yielded as skipped with its reason: a symbolic link, something that is not a regular file, a file with no picture extension, a file that vanished, a file that cannot be read. Verify: `tests/unit/test_folder_walk.py` builds a fixture tree with a picture, a text file, a file with a lying extension, a symlink inside the tree, a symlink out of it, a symlink to a parent directory, a fifo and a subdirectory, and asserts the exact classification of each, with and without the recursive flag.
- [x] 1.2 The walk is sorted and terminates on a tree containing a link to its own parent (design decisions 10 and 3). Verify: the same unit test asserts the order of what it yields and that each real file is read exactly once.
- [x] 1.3 A directory that does not exist, is not a directory once resolved, or cannot be read is refused before anything is walked, naming it. Verify: unit tests for all three, including a directory whose permissions deny reading.
- [x] 1.4 The classification survives a tree that changes under it: the file a candidate names may be replaced between being listed and being opened, and the open is what decides (design decision 2). Verify: `tests/unit/test_folder_walk.py` forces exactly that interleaving through a seam the walk calls before each open — the test replaces the entry with a symlink pointing outside the tree in one case and with a fifo in another — and asserts that nothing outside the tree is read, that the run does not block, and that both are reported as skipped.
- [x] 1.5 A directory with no entries, and a directory whose entries are all skipped, both complete with a summary of zeros rather than an error. Verify: unit tests for both.
- [x] 1.6 A run named with a symbolic link to a directory is resolved once and walked as that directory; a link to something that is not a directory is refused by task 1.3's rule. Verify: unit tests for both.

## 2. Importing a file through the pipeline

- [x] 2.1 Extend `app/services/folder.py` with the per-file import: hand `create_asset` the open descriptor, `source = folder`, the file's own name as `original_filename`, the run's tags, and the run's metadata with the recorded relative path merged last (design decision 7). Nothing in `app/services/assets.py` changes. Verify: an integration test imports a folder and asserts the stored asset equals the same picture uploaded over HTTP in every stored value except `source` and the recorded origin; `git diff --stat main..HEAD -- app/services/assets.py` is empty.
- [x] 2.2 The run's tags and metadata are validated once, before the walk starts, through the same normalisation an upload uses; an unacceptable value refuses the run with nothing stored. Verify: unit tests for a bad tag and for oversized metadata, and an integration test asserting the store is untouched after such a refusal.
- [x] 2.3 A file whose recorded path would push its metadata past the bound is refused with that reason, and the run continues. Verify: an integration test with a deep enough path.
- [x] 2.4 Metadata given for the run cannot replace the recorded origin: the import's key wins (design decision 7). Verify: an integration test importing with metadata that names that key.
- [x] 2.5 A zero-byte file with a picture's extension is refused as undecodable, exactly as an upload of no bytes is. Verify: an integration test asserting the reason and that nothing was stored.
- [x] 2.6 Every outcome per file — created, already stored, refused with the reason, skipped with the reason — is recorded in a report object, and the run never stops at the first failure. Verify: an integration test over a mixed fixture tree asserts every count and every reason.

## 3. The dry run

- [x] 3.1 A dry run walks, opens, hashes, inspects and looks the hash up, and writes nothing: no file under the media root, no asset, no job, no change to an existing asset (design decision 6). Verify: an integration test snapshots the media root and the three tables before and after, and asserts both are unchanged while the report names what would have been created.
- [x] 3.2 The dry run's verdicts equal the real run's: for the same tree, what it says would be created, refused or already stored is what a real run then does. Verify: an integration test runs both over one fixture tree and compares the reports field by field.

## 4. Claiming the work this run created

- [x] 4.1 Add an optional set of asset identifiers to `IndexingJobRepository.claim` and `claim_statement`, and pass it through `app/services/indexing.py::run_batch` and `drain`. A claim without it behaves exactly as before (design decision 8). Verify: an integration test claims with a restriction from a queue holding older due work for other assets and asserts it took only the named assets' work; the existing claim tests of change 6 stay green unchanged.
- [x] 4.2 The restricted claim keeps every property of an unrestricted one — one runner at a time, the lease, the attempt count, `SKIP LOCKED`. Verify: an integration test runs two restricted claimers over one asset's work concurrently and asserts exactly one of them took it, once.
- [x] 4.3 `app/services/folder.py` finishes the work it created: read the state of its own assets' work, stop when none is `pending` or `running`, otherwise claim and execute another restricted batch; stop and report when a pass claims nothing while its work is unfinished, and bound the number of passes (design decision 8). Verify: an integration test with a queue already holding more due work for other assets than one batch can take asserts the imported assets end with vectors and that the run did not report success while its own work was unfinished.
- [x] 4.4 The import never waits out a backoff: work that failed an attempt while the queue permits another is reported as still queued with that reason, and the run ends (design decision 8). Verify: an integration test with the default attempt bound in which the model fails once asserts the command returned promptly, the asset exists, its work is `pending` and due later, and the summary counts it as still queued — not as failed and not as indexed.
- [x] 4.5 Work whose attempts are spent is reported as failed with the reason the queue recorded, and a failed job does not fail the import. Verify: an integration test with one permitted attempt in which the model fails asserts the import succeeded, the asset exists, the job is `failed`, and the summary reports it as failed with that reason.
- [x] 4.6 The summary reports the three states separately — indexed, still queued, failed — and never conflates them. Verify: an integration test over one import that produces all three asserts each count and each reason.

## 5. The command

- [x] 5.1 Add `index-folder` to `app/cli.py`: the directory argument, `--recursive`, `--tags`, `--meta`, `--dry-run`, `--no-index`; it builds the settings, storage, session factory and inference pool, calls the service and prints the report through a `describe`-style renderer, as `storage prune` does. Verify: `uv run semanticshelf index-folder --help` pasted into the commit body, and a CLI test asserting the summary's lines for a fixture tree.
- [x] 5.2 Exit status: 0 when the run completed, even with refusals; non-zero when it could not run at all (design decision 9). Verify: CLI tests asserting both, including the exit code for a missing directory.
- [x] 5.3 `--no-index` leaves the work queued: the assets exist, their work is `pending`, no vector is written, and the summary says so. Verify: an integration test.
- [x] 5.4 Progress is shown for both phases with `click`'s progress bar, and no new dependency is added. Verify: the command run by hand with its output pasted into the how-to; `make lock-check` green.

## 6. Failing inputs (high tier: one per new check)

One row per new guard, one probe per row; each removes exactly that guard,
runs the named test, records the output in the commit body and restores the
code.

| New check | Probe |
|---|---|
| The open refuses a symbolic link (`O_NOFOLLOW`) | 6.1 |
| The open cannot block (`O_NONBLOCK`) | 6.2 |
| What is validated is the descriptor (`fstat`), not the path | 6.3 |
| The walk does not enter a symlinked directory | 6.4 |
| The walk is relative to the directory's descriptor | 6.5 |
| The named directory is resolved once, before the walk | 6.6 |
| Candidates are chosen by extension | 6.7 |
| Tags and metadata are validated before the walk | 6.9 |
| The recorded origin is not overwritten by the run's metadata | 6.10 |
| `original_filename` stays a bare name | 6.11 |
| A dry run writes nothing | 6.12 |
| A refusal does not stop the run | 6.13 |
| A missing directory exits non-zero | 6.14 |
| A claim restricted to assets takes only their work | 6.15 |
| The import waits for its own work, not for any work | 6.16 |
| The import's wait is bounded | 6.17 |
| Still queued and failed are not conflated | 6.18 |

- [x] 6.1 Open without `O_NOFOLLOW`: the outside-symlink test fails, showing a file from beyond the tree stored.
- [x] 6.2 Open without `O_NONBLOCK`: the fifo test fails by hanging until its timeout.
- [x] 6.3 Decide from an `lstat` on the path instead of `fstat` on the descriptor: the mutation-race test of task 1.4 fails.
- [x] 6.4 Pass `followlinks=True` to the walk: the parent-link test fails or does not terminate within its timeout.
- [x] 6.5 Open by full path instead of relative to the directory descriptor: the mutation-race test that swaps a parent directory for a link fails.
- [x] 6.6 Walk the named path without resolving it: the symlinked-root test fails.
- [x] 6.7 Accept every regular file as a candidate: the test that a document is skipped rather than refused fails.
- [x] 6.8 **No probe, and why.** The rule it named — the bytes decide what a file is — is enforced by the inspection inside the pipeline this change only feeds, and change 5 demonstrates it with its own probe (`ea0c781`). Removing it is not an edit inside this change's diff, so a probe here would be theatre. The behaviour is still asserted: `tests/integration/test_folder_import.py` stores nothing for `lying.png`, a text file named like a picture, and `tests/unit/test_folder_walk.py` shows the walk opening it regardless of its name.
- [x] 6.9 Validate the tags after the walk instead of before: the test that a bad tag leaves the store untouched fails.
- [x] 6.10 Merge the run's metadata last: the test that the recorded origin survives fails.
- [x] 6.11 Put the relative path in `original_filename`: the test that the field holds a bare name fails.
- [x] 6.12 Let the dry run call `create_asset`: the snapshot test fails.
- [x] 6.13 Re-raise the first refusal: the mixed-tree test fails, showing a run that stopped.
- [x] 6.14 Exit 0 for a missing directory: that CLI test fails.
- [x] 6.15 Ignore the asset restriction in the claim: the restricted-claim test fails, showing another asset's work taken.
- [x] 6.16 Decide the import is finished by the number of batches rather than by the state of its own assets: the test of task 4.3 fails, showing a run that returned with its own work pending.
- [x] 6.17 Remove the "a pass that claimed nothing ends it" rule: the test that an import whose work is held by another runner still returns fails by hanging until its timeout.
- [x] 6.18 Report every unfinished job as failed: the test of task 4.4 fails, showing a retriable job counted as a terminal failure.

## 7. Documentation and the requirement amendments

- [x] 7.1 Extend `docs/how-to/indexing.md` with the import: the command, its options, the summary, the dry run, what is skipped and why, and what "still queued" means. Verify: every command run in its exact form, output pasted from the run, the file re-read whole afterwards.
- [x] 7.2 Add the command to `docs/reference/commands.md`. Verify: the row matches `--help` word for word.
- [x] 7.3 Amend FR-CLI-1 in `docs/explanation/requirements.md`: the relative path is metadata and `original_filename` keeps its guarantee; `INDEXING_RUNNER` arrives with change 13 and `--no-index` stands in for it until then. Verify: `rg "original_filename" docs/ openspec/` shows no surviving claim that it holds a path.
- [x] 7.4 The tier correction of row 7 (made when this change was proposed) still holds at the end. Verify: `rg -n 'add-folder-indexing-cli' openspec/ROADMAP.md docs/explanation/requirements.md` shows `high` in both, and `proposal.md` agrees.
- [x] 7.5 Write `docs/adr/ADR-004-*.md`: a claim may be restricted to named assets, why an operator command needs it, what it costs (a runner can take its own work ahead of older work), and what it does not change (one runner at a time, the lease, the retries, the order among what a claim may take). It refines ADR-003's "first due, first served", which is why it is a record rather than an edit — ADR-003 is append-only. Verify: re-read whole; the ADR index lists it; `rg -n "first due" docs/` shows the sentence only in ADR-003, with ADR-004 naming the refinement.

## 8. Wrap-up

- [x] 8.1 Commits per logical block, no agent trailers, each body naming the evidence for the tasks its diff holds. Verify: `git log --format=%B main..HEAD | grep -c '^Co-Authored-By'` prints `0`.
- [x] 8.2 `env -u DATABASE_URL make check` green and `make test-integration` green against pgvector. Verify: both outputs recorded in a commit body.
- [x] 8.3 Acceptance on GitHub (the user pushes the branch): both jobs green. Verify: the user reports the run.
- [x] 8.4 `openspec validate add-folder-indexing-cli --strict` and `scripts/pregate-verify.sh gate2 add-folder-indexing-cli` pass; request Gate 2 with `/gate-review add-folder-indexing-cli 2`.
