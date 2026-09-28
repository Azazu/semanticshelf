# Review — stretch-style-search

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-28
**Reviewed-Commit:** f8e62d57fd00dc57c0a5a9de84c4e1ae80134fd2
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `specs/embedding-models/spec.md:28-32`; `tasks.md:41-44` | The new requirement permits a key only after its margin is measured against every existing key, but the benchmark and decision tasks compare CSD only with `dinov2-large`. `clip-vit-l14` is also a stored image-vector key in `app/domain.py`. Measure it under the same question or narrow the requirement and justify why that key is excluded; otherwise the planned ADR cannot establish the scenario it is meant to satisfy. | open |
| 2 | major | `design.md:94-112`; `tasks.md:35-40` | Leaning is a ratio of cosine-similarity means, which can be zero or negative even when both pair sets are nonempty. A zero denominator makes the decision undefined; a negative denominator can reverse the ordering, and a nonpositive incumbent makes the 3× bound vacuous. Define the metric and decision for these cases before the full run, then add tests for those values. | open |
| 3 | minor | `design.md:60`; `tasks.md:5-11` | The applicability table says a blank image produced by a look is embedded like any other image, while task 1.1 requires refusing that look. Choose one corpus rule and make the design and verification task agree. | open |
