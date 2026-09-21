# Handoff — add-embedder-protocol-and-clip

**Updated:** 2026-09-21 · claude
**State:** awaiting-gate-2
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

Gate 2 round 1 came back `changes-requested` with three `major` findings;
all three are fixed and the confirmation of round 1 is requested next.

1. List settings were unreadable from the environment (a complex type is
   JSON-decoded before validators run) — both fields are `NoDecode` now, and
   the tests go through the environment and a dotenv file.
2. Three sequential checks broke the probe's own "about twice the timeout"
   bound — the two that need the database run concurrently, with a timing
   test.
3. The tracked configuration template still named the superseded settings —
   the developer replaced the block (the security tooling blocks an agent
   from writing that file); the application starts with exactly those values.

## Blockers

None.
