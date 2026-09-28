# Handoff — stretch-style-search

**Updated:** 2026-09-28 · claude
**State:** proposing
**Branch:** change/stretch-style-search

## Done this session

- Branch `change/stretch-style-search` created off `main`, which carries the
  whole plan and stretch 17 archived.
- Change scaffolded with `openspec new change` (schema `spec-driven`).
- `openspec/ROADMAP.md` already carries this as stretch row 18, and
  `docs/explanation/requirements.md` §9 as the same row — left as they are.

## Next step

`/opsx:propose stretch-style-search` — a style embedding as a **third storage
key**, with its own width, its own CHECK and its own partial index, reachable
through `model=` on the picture searches.

This one is the opposite shape to change 17, and the proposal has to say so:
an encoder answered in a space that already existed and stored nothing, while
a style model has a space of its own. That means a migration, an index, a
re-index of the corpus and a second vector per asset — every mechanism ADR-001
and ADR-002 built, used for the first time by a key that is not CLIP or
DINOv2. Three questions the proposal owes an answer to before anything is
built: which checkpoint (and what "style" means for it), what evidence would
show it ranks by style rather than by subject where DINOv2 already ranks by
appearance, and whether it earns its width in this project at all.

## Blockers

None.
