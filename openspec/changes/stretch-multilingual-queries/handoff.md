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

- The four artifacts are written, and the feasibility question they rest on was
  **probed before they were written**, not assumed: the package the model card
  recommends (`multilingual-clip` 1.0.10, 2022) does not load under this
  project's transformers 5.17, while the model itself — XLM-RoBERTa large, mean
  pooling, one linear layer into CLIP ViT-L/14's space — assembles by hand from
  the main revision's checkpoint with 0 missing tensors and answers at width
  768. Four concepts in Russian returned what English returned, against vectors
  already in the store. The probe's table is in `design.md` Context.
- **Risk-Tier: high** — a model download is egress from a process this
  repository ships, and the change widens what the search endpoint accepts.
  Gate 1 is required before implementation.

## Next step

`/gate-review stretch-multilingual-queries 1` — Gate 1 on the artifacts.
`scripts/pregate-verify.sh gate1 stretch-multilingual-queries` passes (19
tasks, tier declared, applicability table present, links resolve).

## Blockers

None.
