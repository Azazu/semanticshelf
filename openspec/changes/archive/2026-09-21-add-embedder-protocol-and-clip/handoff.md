# Handoff — add-embedder-protocol-and-clip

**Updated:** 2026-09-21 · claude
**State:** merged
**Branch:** change/add-embedder-protocol-and-clip

## Done this session

- Task group 3 — `app/ml/registry.py` (lazy per-process cache, one lock per
  key, stored only on success) and `app/ml/pool.py` (the bounded pool that
  loading and inference both run on), wired into the lifespan with warm-up.
- Task group 4 — `app/ml/clip.py`: both towers, explicit cache directory,
  batching, `torch.inference_mode()`, truncation by tokenising twice, the
  checkpoint-width guard at load, and the runtime imported inside the
  functions that use it. `make test-models` passes against the real weights;
  the first run caught that transformers 5.17 returns an output object rather
  than a tensor.
- Task group 5 — the readiness `models` check: the schema's dimension
  constraint against the application's declarations, skipped when the
  database check failed, loading nothing.
- Task group 6 — `app/cli.py` with `models warm` under the `semanticshelf`
  console script; `docs/how-to/models.md`; the settings, command and index
  documents; the AGENTS.md layout and Embedder line.
- Task group 7 — every failing input demonstrated (7.3, 7.4, 7.6, 7.7, 7.8),
  outputs in the commit bodies, code restored, caches cleared.
- Task group 8 — `docs/explanation/requirements.md` amended: FR-IDX-1,
  FR-MDL-4, FR-MDL-7 as the proposal states, plus four sibling claims that
  were false against this code (FR-MDL-1, FR-MDL-3, FR-MDL-5, FR-MDL-6).
- Task group 9 — `enable-cache: true` on the setup-uv step; actionlint 1.7.12
  (pinned by digest) exits 0.

Local evidence: `env -u DATABASE_URL make check` 118 passed;
`make test-integration` 24 passed; `make test-models` 7 passed;
`openspec validate --all --strict` 5 passed; both script suites and `sh -n`
over every script clean; `scripts/pregate-verify.sh gate2` fails only on the
two tasks that the push and the gate request themselves close.

## Next step

Merged into `main` as `eda06c6` and archived. The specs it introduced live
in `openspec/specs/embedding-models/spec.md`; the readiness requirement it
changed lives in `openspec/specs/health-probes/spec.md`.

## Blockers

None.
