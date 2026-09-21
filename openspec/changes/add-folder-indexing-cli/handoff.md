# Handoff — add-folder-indexing-cli

**Updated:** 2026-09-21 · claude
**State:** ready-to-merge
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

Gate 2 passed: Confirmation 3 of round 1 on `f91ae83` reads `confirmed`, both
findings resolved.

The branch has moved since the CI run that was green (`c1faee6`): three fixes,
their tests, the probes and the artefacts. Push it again so CI runs on the head
Gate 2 confirmed, then `/git:merge add-folder-indexing-cli`, then
`/opsx:archive`.

Local evidence: `env -u DATABASE_URL make check` green (275 tests);
`make test-integration` green (149 tests); all 20 probes of group 6 caught
their removal; nothing left running after any probe.

## Blockers

None.
