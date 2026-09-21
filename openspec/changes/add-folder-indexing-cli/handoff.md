# Handoff — add-folder-indexing-cli

**Updated:** 2026-09-21 · claude
**State:** proposing
**Branch:** change/add-folder-indexing-cli

## Done this session

- Branch and scaffold created. The work, from roadmap row 7 and
  `docs/explanation/requirements.md` §2.7 (FR-CLI-1): `index-folder <dir>`
  walks a folder and feeds every JPEG, PNG and WebP through the same pipeline
  an upload goes through — the same inspection, the same storage rules, the
  same duplicate check by content hash, the same work queued per enabled
  model — with `--recursive`, `--tags`, `--meta`, `--dry-run`, `source =
  folder`, the file's relative path kept as the original filename, and a
  summary of what was created, skipped as a duplicate and refused with its
  reason. With the background runner it then drains the queue before exiting.

## Next step

`/opsx:propose add-folder-indexing-cli` — proposal, spec delta, design and
tasks. Tier is `medium` by the roadmap, but the proposal has to argue it: the
command reads paths the user supplies, which is the one place this change
touches input handling, and that is a `high` trigger in AGENTS.md if a path a
client controls can reach the media root.

## Blockers

None.
