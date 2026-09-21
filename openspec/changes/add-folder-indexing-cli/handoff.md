# Handoff — add-folder-indexing-cli

**Updated:** 2026-09-21 · claude
**State:** fixing-g2
**Branch:** change/add-folder-indexing-cli

## Done this session

Gate 1 passed after one round and two confirmations; task groups 1-7 are
complete, 47 of 51 tasks checked.

- `app/services/folder.py`: the walk (`os.fwalk`, a descriptor-relative
  `O_NOFOLLOW | O_NONBLOCK` open, `fstat` on the descriptor), the per-file
  import through `create_asset`, the dry run that reads everything and writes
  nothing, the report, and the loop that finishes the work the run created.
- `app/repositories/jobs.py` and `app/services/indexing.py`: a claim may name
  the assets whose work it wants. Every existing caller is untouched and its
  tests stayed green as written.
- `app/cli.py`: `index-folder` with `--recursive`, `--tags`, `--meta`,
  `--dry-run`, `--no-index`, two progress bars and an exit status that is
  non-zero only when the run could not start.
- 17 probes, each removing one guard; three of them were wrong the first time
  and each correction is in the commit body of `1fe86a9` (a probe that checked
  after the race, a probe that edited the wrong function — the harness now
  refuses an ambiguous match — and a probe whose guard was not the one
  bounding the loop).
- Task 6.8 has no probe and says so: the rule it named lives in change 5's
  inspection and was demonstrated there.
- ADR-004, the how-to walkthrough run against real CLIP weights, the command
  in the reference, and FR-CLI-1 amended twice.
- Security-sensitive surface: path handling (the walk) and input handling (the
  pipeline it feeds), which is why the tier is `high`.

## Next step

Gate 2 round 1 on `c1faee6`: `changes-requested`, one blocker and one major,
recorded in `review.md` as commit `5b28341`. Both are real.

1. **blocker** — the run resolves its root three times (`import_folder` for the
   report, `walk` again, and `count_entries` from the CLI a third), so a path
   replaced between them can send the walk into a different tree than the one
   the report names. The design's "resolved exactly once" was written and not
   implemented. The fix is to resolve once, open a descriptor for that
   directory, and walk relative to it — the same answer the per-file open
   already uses, applied to the root.
2. **major** — a dry run classifies each file against the database alone, so
   two files with identical bytes in one folder are both reported `created`
   while a real run stores the first and counts the second `already stored`.
   The dry run has to remember the hashes it has already called new.

`/workflow:fix-findings add-folder-indexing-cli`, then a confirmation of
round 1.

## Blockers

None.
