# Handoff — add-demo-dataset

**Updated:** 2026-09-22 · claude
**State:** awaiting-gate-2
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

Gate 2 round 1 returned three findings — two majors and a minor — and all three
were real defects in the sidecar work:

1. A sidecar that **vanished** between the walk listing it and the open was
   treated as "this picture has no sidecar", so the picture was imported
   without the provenance the run had already seen it carry. `_read_sidecar` is
   only ever called for a name the walk just listed, so every failure there is
   a refusal now, and the spec gained the scenario.
2. A **dry run** combined the sidecar's tags with none of the run's, while the
   real import combines them with all of them: 32 run tags plus one sidecar tag
   pass the rehearsal and are refused for real. The rehearsal now takes the
   run's tags, and a test runs the same folder both ways.
3. The **progress total** counted sidecars that the walk never reports, so a
   bar ended one short per pair. The counter and the walk now share one rule
   (`_sidecars_in`), and a test asserts they agree.

Each fix has a demonstrated failing input: undo it and its test fails.

Run: `/gate-review add-demo-dataset 2 confirm 1`. The user pushes first — the
code changed.

Local evidence, run the way CI runs it (`FORCE_COLOR=1 CI=true`, the difference
that made the last push red): `make check` 406 green,
`make test-integration` 198 green, `openspec validate --all --strict` 13/13.

## Blockers

None.
