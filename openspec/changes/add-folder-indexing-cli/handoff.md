# Handoff — add-folder-indexing-cli

**Updated:** 2026-09-21 · claude
**State:** awaiting-gate-1
**Branch:** change/add-folder-indexing-cli

## Done this session

Gate 1 round 1 (`f010e59`) came back `changes-requested` with six findings —
two blockers, four majors. All six were real; none is marked `wont-fix`.

- **1, blocker — the check and the open were of a path, not of a thing.** The
  walk now uses `os.fwalk`, opens each candidate relative to that directory's
  descriptor with `O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC`, and decides
  what the file is from `os.fstat` on the descriptor it will read. Measured on
  Python 3.12.14 and recorded in `design.md`: a symlink is refused by the
  kernel with `ELOOP`, a fifo opens without blocking and is then rejected as
  not a regular file, and the bytes read come from that same descriptor. A task
  (1.4) forces the swap between listing and opening, and probes 6.1, 6.2, 6.3
  and 6.5 remove each half of the mechanism.
- **2, blocker — the import could not promise vectors through `drain`.** It
  claims whatever the queue offers, so older work would swallow every pass.
  The claim gains an optional set of asset identifiers (a delta on
  `indexing-jobs`), and the import loops over the state of its **own** assets,
  stopping when none is unfinished or when a pass claims nothing. The
  guarantee is now stated as what it is: every asset it created ends with a
  vector or with work the queue still owns, and the summary says which.
- **3, major — the symlink policy contradicted itself.** One rule now: regular
  files only, every symlink skipped and reported. Containment became structural
  rather than a `resolve()` comparison.
- **4, major — "indistinguishable from an upload" was false.** The requirement
  now names the two differences exactly: the source and the recorded origin.
- **5, major — the applicability table claimed tests that did not exist.** The
  outcomes for an empty directory, a directory with no candidates, a zero-byte
  file and a symlinked root are defined in the spec and carry tasks 1.5, 1.6
  and 2.5, with probe 6.6 for the new root-resolution guard.
- **6, major — "every asset has vectors" and "a failure does not fail the
  import" could not both hold.** Rewritten as above, with a scenario and task
  4.4 for work that fails every attempt.

Swept for siblings: ADR-003 states "first due, first served", which a
restricted claim refines — task 7.5 writes ADR-004 rather than editing an
append-only record. `tasks.md` is 48 tasks now, 17 of them probes.

## Next step

Confirmation 1 of round 1 (`1f3d145`): five findings `confirmed`, finding 6
still `changes-requested` — and right again. The requirement allowed a return
with work queued, but its happy-path scenario still demanded vectors for every
asset unconditionally, and task 4.4 demanded a terminal failure that the
queue's own backoff makes unreachable without sleeping through it.

Fixed by stating the policy instead of hiding it: **the import never waits out
a backoff.** A failure with attempts left is reported as still queued with that
reason; a failure with the attempts spent is reported as failed with the
queue's reason; the two are never conflated. The happy-path scenario now says
"a folder whose work all succeeds", and tasks 4.4, 4.5 and 4.6 cover the
retriable path, the terminal path (one permitted attempt) and the summary that
keeps them apart, with probe 6.18 for the conflation.

Second confirmation of round 1: `/gate-review add-folder-indexing-cli 1
confirm 1`. If it comes back `changes-requested` on finding 6 again, that is
the second failed confirmation on one finding — the protocol says stop and ask
you to arbitrate rather than loop.

## Blockers

None.
