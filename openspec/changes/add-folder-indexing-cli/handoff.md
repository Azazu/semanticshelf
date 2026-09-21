# Handoff — add-folder-indexing-cli

**Updated:** 2026-09-21 · claude
**State:** awaiting-gate-2
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

Gate 2 round 1's two findings are fixed on `9e69d2e`:

1. the root is resolved once, opened, and every step — count, walk, report —
   works from that descriptor, so a name taken over mid-run cannot redirect
   anything (probe 6.19, and 6.6 repointed at what the resolution still buys);
2. a rehearsal remembers the hashes it has already called new, so two files of
   identical bytes in one folder are reported exactly as a real run reports
   them (probe 6.20).

Confirmation of round 1: `/gate-review add-folder-indexing-cli 2 confirm 1`.

Local evidence: `env -u DATABASE_URL make check` green (271 tests);
`make test-integration` green (149 tests); all 19 probes of group 6 caught
their removal on a full re-run, and nothing was left running afterwards.

## Blockers

None.
