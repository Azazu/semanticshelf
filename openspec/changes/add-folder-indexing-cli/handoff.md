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

The branch is pushed and its CI run is green (reported by the user), so all 51
tasks are checked. Gate 2 requested with `/gate-review add-folder-indexing-cli
2`; the verdict and its findings are recorded in `review.md` by the runner.

Local evidence, every check CI runs: `openspec validate --all --strict` (10
items), every `scripts/*_test.sh`, `sh -n scripts/*.sh`,
`env -u DATABASE_URL make check` (269 tests) and `make test-integration`
(148 tests) — all green.

One operational note from this session: two probes are meant to hang, and the
runner's timeout used to kill `uv` while leaving `pytest` spinning. The runner
now starts each probe in its own process group and kills the group; the
orphans it had left were stopped.

## Blockers

None.
