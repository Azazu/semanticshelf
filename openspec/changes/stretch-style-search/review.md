# Review — stretch-style-search

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** f8e62d57fd00dc57c0a5a9de84c4e1ae80134fd2
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `specs/embedding-models/spec.md:28-32`; `tasks.md:41-44` | The new requirement permits a key only after its margin is measured against every existing key, but the benchmark and decision tasks compare CSD only with `dinov2-large`. `clip-vit-l14` is also a stored image-vector key in `app/domain.py`. Measure it under the same question or narrow the requirement and justify why that key is excluded; otherwise the planned ADR cannot establish the scenario it is meant to satisfy. | fixed |
| 2 | major | `design.md:94-112`; `tasks.md:35-40` | Leaning is a ratio of cosine-similarity means, which can be zero or negative even when both pair sets are nonempty. A zero denominator makes the decision undefined; a negative denominator can reverse the ordering, and a nonpositive incumbent makes the 3× bound vacuous. Define the metric and decision for these cases before the full run, then add tests for those values. | fixed |
| 3 | minor | `design.md:60`; `tasks.md:5-11` | The applicability table says a blank image produced by a look is embedded like any other image, while task 1.1 requires refusing that look. Choose one corpus rule and make the design and verification task agree. | fixed |

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** 9d111cf929641dd0e4a139a6129652eab62c38d4
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — the benchmark and decision tasks now measure `clip-vit-l14` and `dinov2-large`, derive the stored image keys from `app.domain`, and record every incumbent in the ADR. |
| 2 | changes-requested — the deciding rank preference and diagnostic ratio handle the zero and negative denominator cases, but task 2.4 requires a test where a candidate clears the headroom bound while scoring below 0.5. This is impossible: preference scores lie in [0, 1], so every incumbent is at least 0 and `incumbent + (1 - incumbent) / 2` is at least 0.5. Replace that test with a feasible boundary case; as written, the Gate 1 implementation plan cannot be completed. |
| 3 | confirmed — the design and task 1.1 now both refuse a constant picture for that photograph. |

## Confirmation 2 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** eb3f588328bfd032d6ef7f673c2a78579247191f
**Verdict:** confirmed

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — the diff retains the comparison against both stored image keys and the task to derive them from `app.domain`; the ADR task still requires every incumbent's result. |
| 2 | confirmed — task 2.4 replaces the impossible below-0.5 case with feasible tests below, on, and above the strict headroom bound, including an incumbent of 0 and selection of the highest incumbent. The design uses the same single bound; task 2.3 still covers zero and negative diagnostic denominators. |
| 3 | confirmed — the corpus rule remains consistent: the design and task 1.1 both refuse a constant picture for that photograph. |

## Round 2 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** f12e7fb6b035d0ecc8747117edef5a28524982ba
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `design.md:227-240`; `tasks.md:67-79` | The proposed cache fingerprint does not identify the actual CLIP and DINOv2 checkpoints or their processors. Both incumbent adapters load configurable model names without a pinned revision (`app/ml/clip.py` and `app/ml/dinov2.py`), so changing a configured name or receiving new weights at the same name can leave the fingerprint unchanged and reuse vectors from a different model. The claimed equivalence between a cached run and a fresh run therefore does not hold. Bind each cache entry to the effective checkpoint and preprocessing identity for every model, or narrow the cache guarantee and ensure the published run recomputes vectors; add a test that changes an incumbent's model identity. | fixed |

## Confirmation 1 · Gate 1 · Round 2
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** 95298a9d35967cdc37752140f6eb305bfb1ab644
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | changes-requested — the new fingerprint includes the configured incumbent name and a commit hash resolved from the local model cache, but it does not bind that hash to the weights and processor actually used. Both adapters call `from_pretrained(name, cache_dir=cache)` separately for the processor and model, without a revision, so the two loads can resolve different snapshots and a later cache lookup can report a snapshot different from either load. The processor's behavior also depends on the installed `transformers` version, which the fingerprint omits. Resolve an immutable revision before loading and use it for both objects, or identify both loaded objects directly; include the preprocessing implementation version (or recompute on a version change). Add tests for a changed resolved revision and for these identity mismatches so a cache hit cannot reuse vectors from different weights or preprocessing. |
