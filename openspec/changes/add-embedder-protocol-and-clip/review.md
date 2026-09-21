# Review — add-embedder-protocol-and-clip

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-20
**Reviewed-Commit:** d0d65775e648c09aa88c1a214d780542f0b1e19d
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | blocker | `proposal.md` What Changes 10 / Non-goals; `tasks.md` 1.2; `docs/explanation/requirements.md` FR-IDX-1 | The planned default configuration cannot satisfy the stated scope. The normative requirement makes `ENABLED_MODELS` default to both registered keys, while this change explicitly does not implement DINOv2 and task 1.2 requires startup to reject every enabled key the service does not implement. Thus the no-environment default must reject `dinov2-large`, contradicting the proposal's promise that all new settings have usable defaults. The artifacts also never state the actual eight defaults even though task 1.2 refers to defaults “the proposal states.” Choose a feasible staged default (and reconcile the normative requirement) or include the missing implementation, then specify and test every default consistently across proposal, spec, design, and tasks. | fixed |
| 2 | major | `specs/health-probes/spec.md` Readiness probe; `design.md` decision 9; `docs/explanation/requirements.md` FR-MDL-7 | The proposed readiness mechanism cannot provide the normative “wrong checkpoint is caught before it writes a vector” guarantee. It compares only the application's static key/dimension declaration with the database constraint and explicitly never loads or inspects the checkpoint, so configuring `CLIP_MODEL_NAME` to a checkpoint with a different projection width can still report `models: ok`. Reconcile the guarantee with the mechanism: either add a checkpoint-compatibility mechanism and verification at the appropriate lifecycle point, or amend the normative claim and specify where an incompatible configured checkpoint is rejected before persistence. | fixed |
| 3 | major | `design.md` goal and decisions 4–5; `tasks.md` 3.1–3.3 | The design claims model loading happens off the event loop, but the only specified registry API loads synchronously under its lock, while the pool task and its non-blocking test cover embedding work only. Warm-up task 3.3 checks which keys load, not which thread performs the potentially multi-gigabyte download/deserialization; no task binds first-use loading to the dedicated pool either. Name the execution path for loading (including lifespan warm-up and later first use) and add a verification that a slow load does not block the loop. | fixed |
| 4 | major | `proposal.md` Non-goals; `docs/explanation/requirements.md` FR-MDL-4; `tasks.md` 1.2 and 4.1 | Device behavior is contradictory. The normative requirement says `DEVICE` allows `cuda` (unsupported only in CI), while the proposal makes GPU support a non-goal and describes the adapter as CPU-only; the tasks add `device` but never say whether it is validated, passed to the model/tensors, or restricted to CPU. Decide the supported values and behavior, reconcile the scope with FR-MDL-4, and add implementation and verification coverage for that decision. | fixed |

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-20
**Reviewed-Commit:** 61470edcdbacc4b6b6c216d81f18125bd049dd23
**Verdict:** confirmed

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed |
| 2 | confirmed |
| 3 | confirmed |
| 4 | confirmed |

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-21
**Reviewed-Commit:** 30a418b8641d78ed61bb023b581ebc97343e2204
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `app/core/settings.py:35-39,63-70`; `tests/unit/test_settings_models.py:36-39`; `docs/reference/settings.md:15-16` | The documented environment syntax for both tuple settings is unusable. `pydantic-settings` JSON-decodes complex fields before the `mode="before"` field validator runs, so a real `ENABLED_MODELS=clip-vit-l14` environment variable raises `SettingsError: error parsing value for field "enabled_models"`; `MODEL_WARMUP=clip-vit-l14` and even the documented empty `MODEL_WARMUP=` fail the same way. The passing test supplies the string as a constructor argument and therefore bypasses the environment source that production and `.env` use. This leaves the required enabled-model and warm-up configuration paths nonfunctional. Mark these fields as non-decoded (or otherwise customize the settings source) and test the exact environment/`.env` forms documented for non-empty and empty lists. | open |
| 2 | major | `app/services/readiness.py:143-156`; `specs/health-probes/spec.md` Readiness probe | The probe no longer satisfies its normative upper bound of about twice `READINESS_TIMEOUT_SECONDS`. After a successful database check, `run_checks` awaits migrations and models sequentially, and each gets a fresh full timeout; a slow-but-successful `SELECT 1` followed by two silent catalog queries can therefore take almost three timeouts. Even when the migration check has already timed out, the model check still spends another full timeout. Use a shared deadline or run the two dependent checks concurrently after the database check, and add a timing test for the worst successful-database path. | open |
| 3 | major | `.env.example:14-17`; `docs/how-to/local-development.md:12`; `docs/reference/settings.md:25-39`; `handoff.md:47-51` | The tracked file that the first-run guide tells every developer to copy still exposes the superseded `EMBEDDER_TEXT_IMAGE` and `EMBEDDER_IMAGE_IMAGE` names and says `MODEL_CACHE=.cache/models`, while the implementation ignores the former names and documents `.data/models`. The handoff acknowledges the inconsistency, but all tasks are checked and the change is presented as Gate-2-ready. Update the actual template to the new settings (including the corrected list parsing from finding 1) and verify startup from a copied template, or obtain explicit user acceptance for leaving the public setup path stale. | open |
