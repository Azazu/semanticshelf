# Handoff — add-demo-dataset

**Updated:** 2026-09-23 · claude
**State:** ready-to-merge
**Branch:** change/add-demo-dataset

## Done this session

All 26 tasks. The corpus exists, is licence-filtered, imports through the
ordinary folder import and is searchable — proved by a real run, not only by
tests: 20 pictures fetched in 30 s, 20 indexed, and
"a red stop sign at a junction" puts both stop-sign pictures on top.

What the real manifest settled, which planning could only guess at:

- the archive is 252 907 541 B and the manifest inside it 19 987 840 B, so
  `MEMBER_MAX_BYTES` is comfortable and the design's "~46 MiB" estimate was
  wrong and is corrected;
- **1 279 of the 5 000 pictures** are under an accepted licence; 3 721 are
  refused, which the run reports;
- every `val2017` entry carries `flickr_url` — the open question of `design.md`,
  now struck. It is the original's address on Flickr, so it is what the
  provenance records as `source_url`; the bucket copy identifies nobody.
  `author` stays absent: the manifest has no name for a single picture.

Evidence: `make check` 406 green, `make test-integration` 195 green,
`openspec validate --all --strict` 13/13, both `scripts/*_test.sh`, `sh -n`
over every script. Twelve demonstrated failing inputs across the four guards
that matter (the layering, the manifest, the transfers, the sidecar).

## Next step

**Gate 2 passed** (Confirmation 1 of round 1, commit `2086af4`, all three
findings confirmed; the reviewer reproduced each independently). Gate 1 passed
earlier on the artifacts.

`/git:merge add-demo-dataset`, then `/opsx:archive`. The corpus itself is not
committed — `.data/` is gitignored — so nothing of the 20 pictures or the
241 MiB archive goes with it.

Local evidence, run the way CI runs it (`FORCE_COLOR=1 CI=true`): `make check`
406 green, `make test-integration` 198 green, `openspec validate --all
--strict` 13/13, both `scripts/*_test.sh`, `sh -n` over every script.

## Blockers

None.
