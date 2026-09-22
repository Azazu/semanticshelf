# Handoff — add-demo-dataset

**Updated:** 2026-09-22 · claude
**State:** implementing
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

**Gate 1 passed** (Confirmation 2 of round 1, commit `f03c61a`, all five
findings confirmed). The contract is settled before a line of it exists:

- three bounds, one per kind of object, with an archive failure fatal and a
  picture failure counted;
- the sidecar read through the descriptor the walk holds, never by path;
- a label converted to a tag by this change's own rule, leaving the service's
  normalisation alone;
- a picture whose bytes are already stored left exactly as it is;
- the picture and its sidecar published as one directory rename, so a
  mismatched pair is impossible rather than unlikely.

Run: `/opsx:apply add-demo-dataset`. 26 tasks in seven groups; the first is the
dependency move and the layering test, and nothing in the service may import
the new module.

## Blockers

None.
