# Review — add-tag-and-meta-filters

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** d760236ca902bfd8cb8d48d5a8155b5844f04c27
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | design.md decision 3; tasks.md 3.1, 3.4; specs/text-search/spec.md pagination | The exhaustion probe is explicitly skipped for every full page, but a full page does not prove that the lookahead was obtained. With `limit=20`, suppose the bounded scan finds exactly 20 matching rows while at least 21 exist. The existing `limit + 1` mechanism returns `has_more=false`, and this design skips the probe and the warning because the page is full. It therefore still presents a budget-limited answer as the end of the ranking. Base the decision on whether the pre-threshold scan supplied the required lookahead, accounting for offset and self-exclusion, rather than whether the rendered page is full. Specify the envelope's behavior and add a regression for exactly `limit` matches reached with additional matches outside the scan budget; preserve the no-probe fast path when the lookahead is actually present. | fixed |
| 2 | major | design.md decision 3; tasks.md 3.1–3.3 | Comparing the short answer with the number of assets satisfying only the narrowing cannot establish that the scan stopped early. `nearest_statement` applies `min_score` outside the page, and `_page_of` receives only those surviving rows. For example, ten tagged assets all below the threshold produce an empty answer after a completely exhausted scan; the proposed existence query finds ten matches and falsely reports a scan limit. A nonzero offset likewise requires comparison with the consumed prefix, and a similar-search probe must exclude the query asset and use the selected model. Define the probe inputs and comparison explicitly, retaining pre-threshold scan information so intentional threshold removal is not diagnosed as scan exhaustion. Add tests for threshold-only shortening (including zero surviving hits), an exhausted nonzero-offset page, and self-exclusion, alongside the genuine budget-limited case. | fixed |
| 3 | major | proposal.md Risk-Tier; design.md; tasks.md introduction and validation tasks | The declared medium tier conflicts with AGENTS.md's Security-Sensitive Code rule: any change touching input handling is high tier. Decisions 4–5 introduce a shared validator and raw query/form parsing on four public surfaces, including multipart image search. Binding SQL values is appropriate but does not exempt this work from that rule. Raise the tier to high consistently, add the required applicability table (including empty/zero/null input handling and the applicable boundary questions), and plan demonstrated failing inputs for every new or changed check plus the required security-sensitive commit/handoff flags. A voluntary Gate 1 alone does not satisfy the other high-tier obligations. | fixed |
| 4 | minor | tasks.md 6.1 | `uv run python scripts/…` is a placeholder rather than the exact runnable command required by openspec/config.yaml. Choose the measurement script path and its corpus-size, selectivity, and seed arguments in the plan so the verification and published reproduction command refer to the same concrete invocation. | fixed |

### Validation

Confirmed the current branch is `change/add-tag-and-meta-filters`, HEAD matches
the reviewed commit, and the working tree was clean before this review. Read
AGENTS.md, openspec/config.yaml, every change artifact, the existing text-search
specification, and the current search repository, service, schema and routers.
`scripts/pregate-verify.sh gate1 add-tag-and-meta-filters` passed, including
strict OpenSpec validation. The findings above concern the planned contract
and its verification; implementation and database experiments were not run.
