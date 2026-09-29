# Review — pin-model-revisions

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-29
**Reviewed-Commit:** e6598b9f10652034958df34b641eea403b785dd0
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | design.md, decisions 1–2; tasks.md, 1.1–1.3; specs/embedding-models/spec.md | The planned validation does not require configured revisions to be immutable commits. For example, `CLIP_REVISION=main` with the default name passes both specified checks (nonempty revision and substituted-name binding); the same applies to DINOv2. The installed Transformers `utils/hub.py` explicitly accepts branches and tags as revisions, so passing the same string to two independent calls does not guarantee one snapshot, and retries or later loads can still fetch different weights. Task 1.1 checks only the defaults' hash shape, and task 1.3 checks only argument equality. Require full immutable commit IDs for configured values as well as defaults, state that constraint in the delta spec, and add rejection tests and demonstrated failing inputs for mutable refs for both settings. Hub verification of commit existence can remain out of scope. | fixed |
| 2 | major | proposal.md, Impact; design.md, Goals / Non-Goals and Migration Plan; tasks.md, 3.2 | The unconditional compatibility guarantee conflicts with the required startup rejection. An existing supported deployment that sets only `CLIP_MODEL_NAME` or `DINOV2_MODEL_NAME` to a compatible checkpoint currently starts; after this change it inherits the new default revision and must refuse startup. Thus “nothing is refused that was accepted yesterday”, “No new failure mode”, and “Nothing observable changed” cannot all hold alongside the proposed spec. Passing unchanged API/integration suites does not verify this upgrade case. Resolve the intended compatibility contract before implementation: if the rejection is retained, explicitly document the required pre-upgrade revision configuration, narrow the compatibility claims throughout the artifacts, and add verification of the old custom-name configuration's rejection and the corrected configuration's success. If uninterrupted upgrades for all supported configurations are mandatory, revise the design to satisfy that requirement. This does not require corpus provenance tracking or a database migration. | fixed |

### Validation

- Confirmed the branch is `change/pin-model-revisions`, HEAD matches the reviewed commit, and the initial working tree was clean.
- Read the proposal, design, tasks, delta specification, handoff, repository review rules, OpenSpec configuration, current embedding-models specification, and relevant settings, adapters, documentation and model tests.
- `openspec validate pin-model-revisions --strict` passed.

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-29
**Reviewed-Commit:** 09d7b54545fcd3c0fc7efd91ee6fc61df4fd5886
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — Design decision 1 and the delta specification require full 40-character hexadecimal commits for configured revisions. Task 1.2 covers rejection of branches, tags, abbreviated hashes and malformed/empty values for both settings, plus acceptance of full commits; task 3.1 requires demonstrated failing inputs for these checks. This resolves the Gate 1 validation-plan finding; implementation evidence remains for Gate 2. |
| 2 | changes-requested — Preserving the old custom-name configuration through an explicitly unpinned fallback is a valid resolution direction, and tasks 1.3/3.2 now cover it, but the contract remains contradictory. Task 1.3 requires loading without a revision while task 1.4 still requires that neither adapter ever calls `from_pretrained` without one. The delta's default-revision scenario applies whenever no revision is configured, including the custom-name case its final scenario requires to remain unpinned; its same-snapshot scenario and design decision 2 also promise snapshot identity unconditionally, which the new unpinned path cannot ensure. Scope the default scenario to the default checkpoint name, scope snapshot/retry guarantees and task 1.4 to pinned loads, and explicitly cover the unpinned exception for both adapters. Reconcile the sibling claims in proposal Capabilities and task 2.1 that a substituted name needs a revision, and remove or clearly supersede the startup-refusal rule still presented as a decision in handoff.md. The chosen compatibility policy must be implementable and testable without violating another requirement. |

### Validation

- Reviewed only `e6598b9f10652034958df34b641eea403b785dd0..09d7b54545fcd3c0fc7efd91ee6fc61df4fd5886` and collateral claims reachable from findings 1 and 2; introduced no unrelated findings.
- Confirmed the requested branch and HEAD, a clean initial working tree, and both source findings dispositioned as `fixed`.
- Read the changed planning artifacts, repository review rules and OpenSpec configuration; checked the existing settings and adapter load paths and searched the repository for surviving conflicting claims.
- `openspec validate pin-model-revisions --strict` passed. Structural validation does not resolve the conflicting behavioral requirements above.

## Confirmation 2 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-29
**Reviewed-Commit:** b63357184ba4f928b93d36d63bf3ab911c1d2018
**Verdict:** confirmed

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — Design decision 1 and the delta specification require configured revisions to be full 40-character hexadecimal commit identifiers. Tasks 1.1–1.2 cover defaults, configured full commits, and rejection of mutable, abbreviated, malformed and empty values for both settings; task 3.1 requires demonstrated failing inputs. Task 1.4 preserves the shared immutable revision for both reads of a pinned load. The deliberately unpinned compatibility path is explicitly excluded from this guarantee. |
| 2 | confirmed — The chosen compatibility policy preserves a substituted checkpoint name with no configured revision: it inherits no default revision, loads without one, and reports that it is unpinned. The delta's default scenario now requires the default checkpoint name, and its snapshot scenario, design decision 2 and retry guarantee apply only to pinned loads. Tasks 1.3–1.4 cover both pinned and unpinned calls, task 2.1 explicitly requires the unpinned scenario for both adapters, and task 3.2 verifies the pre-upgrade custom-name configuration still starts. Proposal Capabilities and task 2.1 no longer require a revision for substitution; handoff.md explicitly supersedes the startup-refusal decision. These changes resolve the contradictory requirements identified in the source round and Confirmation 1. |

### Validation

- Reviewed only `e6598b9f10652034958df34b641eea403b785dd0..b63357184ba4f928b93d36d63bf3ab911c1d2018` and collateral effects reachable from findings 1 and 2; introduced no unrelated findings.
- Confirmed branch `change/pin-model-revisions`, HEAD matching the reviewed commit, a clean initial working tree, and both source findings dispositioned as `fixed`.
- Read the changed planning artifacts, repository review rules and OpenSpec configuration; checked existing settings and adapter call sites and searched for surviving conflicting substitution/revision claims.
- `openspec validate pin-model-revisions --strict` passed. This confirms resolution in the Gate 1 plan; implementation and demonstrated failing-input evidence remain for Gate 2.
