# Handoff — stretch-style-search

**Updated:** 2026-09-28 · claude
**State:** awaiting-gate-1
**Branch:** change/stretch-style-search

## Done this session

- Branch `change/stretch-style-search` created off `main`, which carries the
  whole plan and stretch 17 archived.
- Change scaffolded with `openspec new change` (schema `spec-driven`).
- `openspec/ROADMAP.md` already carries this as stretch row 18, and
  `docs/explanation/requirements.md` §9 as the same row — left as they are.

- The four artifacts are written, and the three questions this handoff opened
  with are answered in them — two by a probe run before a word was written.
- **The candidate exists and loads**: `tomg-group-umd/CSD-ViT-L` (CC-BY-4.0,
  declared). Its `config.json` is `{"model_type": "custom"}` and the file is a
  *training* checkpoint in OpenAI CLIP's module layout, so `transformers`
  cannot build it; `open_clip`'s ViT-L-14 visual tower takes the weights with
  nothing missing and nothing unexpected once CLIP's own projection is removed.
  `weights_only=True` refuses the file until four inert types are allowlisted
  (a numpy scalar under its legacy module path, two numpy types and
  `argparse.Namespace`) — the design refuses `weights_only=False` outright.
- **It answers something DINOv2 does not.** Four photographs under six looks:
  CSD leans toward style at 0.92 (same look 0.507 against same picture 0.551),
  DINOv2 at 0.145 (0.104 against 0.718).
- **The scope is reshaped, deliberately.** The roadmap's row 18 says "a third
  key with its own index"; this change **measures and decides**, and shipping
  the key — migration, index, re-index, `model=` on the picture searches — is a
  follow-up proposed only if ADR-006 says yes. The user chose that shape when
  the change was started; the proposal states it and the specs carry the rule
  that produced it.
- **Risk-Tier: high** — a new dependency, a model download, and a decision that
  governs a later migration.

## Next step

`/gate-review stretch-style-search 1` — Gate 1 on the artifacts.
`scripts/pregate-verify.sh gate1 stretch-style-search` passes (15 tasks, tier
declared, applicability table present, links resolve).

## Blockers

None.
