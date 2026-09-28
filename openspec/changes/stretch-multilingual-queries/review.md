# Review — stretch-multilingual-queries

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** d88cfba7594cfb6d2785bb8189e62cc4a0b26590
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `design.md` decision 4; `tasks.md` 3.1–3.2 | The sole acceptance bound is `mean precision@10 >= 0.8 × English mean precision@10`. If the English baseline is zero, an encoder returning no relevant pictures passes; a low baseline also makes a near-random result sufficient. The plan therefore cannot substantiate the promised claim that a language works. Specify a minimum usable baseline and an absolute quality floor or another guard against a trivial pass, and require the benchmark to report the relevant-asset counts for its concepts. | open |
| 2 | major | `design.md` decision 2 and decision 4; `tasks.md` 1.3 and 3.2 | The adapter downloads the checkpoint from the mutable `main` revision while the published measurements are treated as evidence for the stable `mclip-xlmr-l14` key. A fresh deployment may load different weights or tokenizer/config and answer differently from the measured build without a key or documentation change. Pin the model assets to an immutable revision, and record that revision with the benchmark results so the measured encoder is the one deployed. | open |
| 3 | major | `tasks.md` 1.3; `openspec/specs/embedding-models/spec.md` “Text longer than the model's context is truncated and the caller is told” | The new adapter's task covers tokenization and vector properties but omits detection and reporting of tokenizer truncation. `EmbeddingResult.truncated` feeds `query_truncated` in the text-search response; silently cutting an XLM-R query would violate the existing contract. Add implementation and a real-checkpoint test with an over-context query proving the flag is true, alongside an ordinary-query false case. | open |
