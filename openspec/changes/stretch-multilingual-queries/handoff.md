# Handoff — stretch-multilingual-queries

**Updated:** 2026-09-28 · claude
**State:** implementing
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

- **Gate 1 round 1 — three majors, all accepted.** The acceptance bound was
  only relative, so a zero English baseline would have let an encoder that finds
  nothing pass: it is now two conditions (absolute mean recall@10 ≥ 0.5 and
  ≥ 0.8 × the English baseline), over a concept set chosen by rules that look at
  no language's results, with the relevant-asset counts printed per concept. The
  adapter read the mutable `main` revision while the numbers were to be evidence
  about the key: all three files are pinned to
  `40afa80a85e8efa990384a24bbe5a1f6f1cc81b5`, which the benchmark prints and the
  ADR records. And the truncation flag `EmbeddingResult.truncated` — which the
  API answers as `query_truncated` — was missing from the adapter's task; it has
  its own task and a two-input test now.

- **Gate 1 passed** at `0d4115d` (confirmation 3): three majors raised, all
  fixed. The two residual rounds were the same defect this project keeps
  catching — a claim updated in one artifact and left standing in a sibling:
  the metric (precision → recall) in the proposal, the sample size in the
  design, and then the second pinned revision missing from two task
  descriptions that promised it.

## Next step

`/opsx:apply stretch-multilingual-queries` — 20 tasks in five groups, starting
with the encoder table in `app/domain.py` and the adapter. The probe script
that established feasibility is in the session scratchpad, not the repository;
the adapter is written against the artifacts, not copied from it.

## Blockers

None.
