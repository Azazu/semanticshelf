# Review — stretch-multilingual-queries

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** d88cfba7594cfb6d2785bb8189e62cc4a0b26590
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `design.md` decision 4; `tasks.md` 3.1–3.2 | The sole acceptance bound is `mean precision@10 >= 0.8 × English mean precision@10`. If the English baseline is zero, an encoder returning no relevant pictures passes; a low baseline also makes a near-random result sufficient. The plan therefore cannot substantiate the promised claim that a language works. Specify a minimum usable baseline and an absolute quality floor or another guard against a trivial pass, and require the benchmark to report the relevant-asset counts for its concepts. | fixed |
| 2 | major | `design.md` decision 2 and decision 4; `tasks.md` 1.3 and 3.2 | The adapter downloads the checkpoint from the mutable `main` revision while the published measurements are treated as evidence for the stable `mclip-xlmr-l14` key. A fresh deployment may load different weights or tokenizer/config and answer differently from the measured build without a key or documentation change. Pin the model assets to an immutable revision, and record that revision with the benchmark results so the measured encoder is the one deployed. | fixed |
| 3 | major | `tasks.md` 1.3; `openspec/specs/embedding-models/spec.md` “Text longer than the model's context is truncated and the caller is told” | The new adapter's task covers tokenization and vector properties but omits detection and reporting of tokenizer truncation. `EmbeddingResult.truncated` feeds `query_truncated` in the text-search response; silently cutting an XLM-R query would violate the existing contract. Add implementation and a real-checkpoint test with an over-context query proving the flag is true, alongside an ordinary-query false case. | fixed |

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** e67a09269bcffee61d37307d978a15d8efbf193e
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | changes-requested — The new baseline guard, absolute recall floor and per-concept relevant-asset counts address the trivial-pass case in `design.md` and `tasks.md`. The same measurement is still specified inconsistently: `proposal.md` promises precision@k, while the design and tasks require recall@10; `design.md` requires at least 30 concepts, while task 3.1 permits a report with 20. Align these claims so the promised benchmark and its minimum sample are unambiguous. |
| 2 | changes-requested — The M-CLIP checkpoint and tokenizer are assigned an immutable revision, and task 3.2 records it with the results. But decision 2 also constructs the transformer from the config of the separate `xlm-roberta-large` repository without specifying an immutable revision for that fetch. Pin or vendor that config too, and record the complete set of revisions used for the measurement; otherwise a fresh deployment can still load different model assets under the same encoder key. |
| 3 | confirmed — Decision 2 and task 1.3a require per-input truncation reporting at the model context limit. The planned real-checkpoint test covers an ordinary query and an over-context query in one batch, and an API test checks propagation to `query_truncated`. |

## Confirmation 2 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** ae629d8c67a9779fb703cf485681d17176e53be1
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — `proposal.md`, design decision 4 and tasks 3.1–3.2 now consistently specify recall@10 over at least 20 eligible concepts, an English baseline floor, an absolute language floor, a relative language bound and per-concept relevant-asset counts. |
| 2 | changes-requested — Design decision 2 and tasks 1.3 and 3.1–3.2 pin and report both repositories' revisions, but task 4.2 still requires `docs/how-to/models.md` to say the encoder is pinned to **one** revision. That would publish an incomplete description of the measured and deployed encoder, contrary to decision 2's explicit requirement that the models how-to name both revisions. Update task 4.2 to require both repository revisions; make task 3.3 explicitly require both revisions in ADR-005 as decision 2 promises. |
| 3 | confirmed — The truncation requirement and its real-checkpoint and API verification tasks remain in place; this diff does not weaken them. |

## Confirmation 3 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** 0d4115db6b5e23d7f16add729df655064c51813b
**Verdict:** confirmed

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — The proposal, design and tasks consistently require recall@10 over at least 20 eligible concepts, an English baseline floor, absolute and relative language floors, and per-concept relevant-asset counts. The reviewed diff does not weaken these requirements. |
| 2 | confirmed — Tasks 3.3 and 4.2 now explicitly require both repository revisions in ADR-005 and the models how-to. Design decision 4 also names both revisions. This completes the pinning and reporting requirements of the original finding. |
| 3 | confirmed — The adapter and test tasks still require per-input truncation flags and propagation to `query_truncated`; the reviewed diff does not weaken them. |

## Round 2 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** 1a201c06baffa25c813f489c34a457ee01b92fe9
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `app/ml/mclip.py:113-120` | The transformer checkpoint is loaded with `strict=False`, but the returned missing and unexpected keys are discarded. A checkpoint missing a transformer tensor can therefore load with a randomly initialized layer, pass the 768-wide probe, and serve rankings under the measured `mclip-xlmr-l14` key. Reject missing keys and allow only explicitly understood unexpected keys; demonstrate that removing a required tensor makes loading fail. | fixed |
| 2 | major | `app/core/settings.py:85-93`; `app/ml/mclip.py:92-110`; `docs/adr/ADR-005-multilingual-query-encoder.md:40-45` | `MCLIP_MODEL_NAME`, `MCLIP_REVISION`, and `MCLIP_BASE_REVISION` can replace the measured assets while the API still reports the same encoder key. The only runtime check is output width; another 768-wide checkpoint or a changed tokenizer/config can answer differently or fail to align with stored CLIP images, yet ADR-005's published language measurements appear to apply. Bind this encoder key to the measured asset identities, or give substitutions a distinct identity and avoid applying the published claim to them. | fixed |
| 3 | minor | `app/api/search.py:125-140`; `app/schemas/search.py:26-30` | The text endpoint's OpenAPI description still says the query is English and that scores are comparable within a model, and the score field repeats the model-only claim. With the new encoder, the endpoint accepts measured non-English queries and score comparability depends on the `(model, encoder)` pair. Update these public descriptions so they match the response and the new search contract. | fixed |

## Confirmation 1 · Gate 2 · Round 2
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** a2732c398450a93d54774c4bad982838aec9e674
**Verdict:** confirmed

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — The adapter checks the result of `load_state_dict`: every missing tensor is rejected, and only the known `embeddings.position_ids` leftover is allowed among unexpected tensors. Unit cases cover missing and unexpected names, and the real-checkpoint test removes a required transformer weight and expects `CheckpointTensorsError`. |
| 2 | confirmed — The checkpoint and both repository revisions are constants used by the adapter and benchmark; the three substitution settings are removed. ADR-005, the models how-to and settings reference now state that the encoder key is bound to those measured assets. |
| 3 | confirmed — The text endpoint description now covers the enabled encoder's measured languages and states that scores and thresholds belong to the model and encoder pair. The score field and model parameter descriptions use the same pair rule. |
