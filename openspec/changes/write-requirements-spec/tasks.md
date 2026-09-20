## 1. Specification

- [x] 1.1 Write `docs/explanation/requirements.md` as the full technical specification (sections 0–10 plus Appendix A per the agreed structure), in English, recording every row D1–D17 of the Decision record in `proposal.md` as a normative statement; verify by re-reading the whole file once after the last edit, by the traceability table of Appendix A covering every row D1–D17, and by `rg -n -i '<employer and prior work project names>' docs/ openspec/ -g '!tasks.md'` returning nothing.
- [x] 1.2 Verify internal consistency of the specification: every capability named in section 2 has a table in section 3 (or an explicit "no persistence" note), an endpoint group in section 4 and a change in section 7; every change in section 7 has a tier consistent with the triggers in `AGENTS.md`; verify by a checklist pass recorded in the commit body.
- [x] 1.3 Verify the specification against the repository rules it must not contradict: the Stack, Domain rules and Testing blocks of `AGENTS.md`, the context of `openspec/config.yaml`, `docs/how-to/local-development.md`; verify by `rg` for each term the spec fixes (`Celery`, `BackgroundTasks`, `HNSW`, `IVFFlat`, `asyncpg`, `Streamlit`, `MODEL_CACHE`, `has_more`) across `AGENTS.md`, `openspec/`, `docs/` so no sibling artifact states an older rule.

## 2. Roadmap and agent context reconciliation

- [x] 2.1 Update `openspec/ROADMAP.md` to match section 7 of the specification: split, add and re-tier rows as the proposal lists, keep ids stable otherwise; verify by a side-by-side read of section 7 and the roadmap (same change ids, same order, same tiers).
- [x] 2.2 Update the `context` block of `openspec/config.yaml` and the Layout / Domain rules blocks of `AGENTS.md` where they state a rule the specification changed (worker model, UI service, error format); verify with `openspec validate write-requirements-spec --strict` and `rg -n 'Celery' AGENTS.md openspec/config.yaml` returning nothing.

## 3. Wrap-up

- [x] 3.1 Commit per logical block (`docs:` for the specification, `docs(roadmap):` for the roadmap and agent context) without any agent trailer; verify with `git log --format=%B main..HEAD | grep -c '^Co-Authored-By'` printing `0`.
- [x] 3.2 Run `openspec validate write-requirements-spec --strict` and `scripts/workflow-verify.sh merge write-requirements-spec`; both must pass before the handoff reads `ready-to-merge` (low tier: no gate).
