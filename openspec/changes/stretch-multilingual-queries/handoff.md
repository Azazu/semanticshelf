# Handoff — stretch-multilingual-queries

**Updated:** 2026-09-28 · claude
**State:** proposing
**Branch:** change/stretch-multilingual-queries

## Done this session

- Branch `change/stretch-multilingual-queries` created off `main`, which carries
  the whole plan archived through change 16.
- Change scaffolded with `openspec new change` (schema `spec-driven`).
- `openspec/ROADMAP.md` already carries this as stretch row 17, and
  `docs/explanation/requirements.md` §9 as the same row — left as they are.

## Next step

`/opsx:propose stretch-multilingual-queries` — the first stretch row: a
multilingual text encoder behind the existing `Embedder` protocol (a
multilingual CLIP variant as a new model key, or a text tower that lands in
CLIP's space), measured against English CLIP on the demo corpus. The proposal
has to answer what "it works" means here before anything is built: today the
service states an English-query limit as a boundary in the README and in the
specs, so a second text model is a claim that has to be measured rather than
asserted, and the comparison needs a corpus with non-English queries whose
right answers are known.

## Blockers

None.
