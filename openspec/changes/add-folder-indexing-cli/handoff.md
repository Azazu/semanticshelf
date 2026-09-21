# Handoff — add-folder-indexing-cli

**Updated:** 2026-09-21 · claude
**State:** fixing-g1
**Branch:** change/add-folder-indexing-cli

## Done this session

- All four artifacts written and strict-valid: `proposal.md`, the delta specs
  (`folder-indexing` new, `asset-upload` modified), `design.md`, `tasks.md`
  (33 tasks, 12 of them failing-input probes).
- Tier raised to `high` and the plan corrected with it: the command walks a
  directory tree the operator names, which is path handling — an explicit
  `high` trigger in AGENTS.md. Row 7 now reads `high` in `openspec/ROADMAP.md`
  and in §7 of `docs/explanation/requirements.md`.
- Two decisions the user was asked about and settled: the relative path is
  recorded as metadata while `original_filename` keeps the bare-name guarantee
  change 5 built (FR-CLI-1 amended by task 6.3), and the tier above.
- The walk's mechanics were measured rather than assumed on Python 3.12.14 —
  `rglob` does not descend into symlinked directories, `is_file()` follows a
  link while `lstat` does not, a fifo would block an open — and the measurements
  are in `design.md` under Context.
- `scripts/pregate-verify.sh gate1 add-folder-indexing-cli` passes.

## Next step

Gate 1 round 1 on `f010e59`: `changes-requested`, six findings (two blockers,
four majors), recorded in `review.md` as commit `41f4611`. All six are real and
none is a misreading; the two blockers both say the same kind of thing — a
guarantee stated in the artifacts that the named mechanism cannot deliver.

`/workflow:fix-findings add-folder-indexing-cli`, then a confirmation of
round 1.

## Blockers

None.
